import AppKit
import WebKit
import ServiceManagement
import Carbon

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, NSMenuDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var service: Process?
    var output = Data()
    var terminating = false
    var loaded = false
    let smokeTest = CommandLine.arguments.contains("--smoke-test")
    var statusItem: NSStatusItem!
    var statusMenu: NSMenu!
    var monitorStateItem: NSMenuItem!
    var speedItem: NSMenuItem!
    var runItem: NSMenuItem!
    var pauseItem: NSMenuItem!
    var reportItem: NSMenuItem!
    var loginItem: NSMenuItem!
    var stateTimer: Timer?
    var apiBase: URL?
    var sessionToken = ""
    var scheduled = false
    var commandInFlight = false
    let session = URLSession(configuration: .ephemeral)

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appMenuItem = NSMenuItem()
        menu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About Linewatch", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Linewatch", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appMenuItem.submenu = appMenu
        let editItem = NSMenuItem()
        menu.addItem(editItem)
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        NSApp.mainMenu = menu
        configureMenuBar()

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1260, height: 850), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Linewatch — Broadband Monitor"
        window.minSize = NSSize(width: 820, height: 620)
        window.center()
        window.isReleasedWhenClosed = false
        window.delegate = self
        webView = WKWebView(frame: .zero)
        webView.navigationDelegate = self
        window.contentView = webView
        let loginLaunch = NSAppleEventManager.shared().currentAppleEvent?.paramDescriptor(forKeyword: AEKeyword(keyAELaunchedAsLogInItem)) != nil
        if !loginLaunch && !CommandLine.arguments.contains("--background") { showDashboard() }
        else { NSApp.setActivationPolicy(.accessory) }
        startService()
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) { [weak self] in
            guard let self = self, !self.loaded else { return }
            self.fail("The local monitor did not start in time. Check Application Support/Linewatch/logs/app.log.")
        }
    }

    func startService() {
        guard let resources = Bundle.main.resourceURL else { return fail("The app resources are missing.") }
        let process = Process()
        process.executableURL = resources.appendingPathComponent("engine/linewatch-engine")
        process.arguments = ["serve"]
        let pipe = Pipe()
        process.standardOutput = pipe
        let root = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Linewatch/logs")
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let log = root.appendingPathComponent("app.log")
        if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
        if let handle = try? FileHandle(forWritingTo: log) { handle.seekToEndOfFile(); process.standardError = handle }
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            DispatchQueue.main.async {
                guard let self = self, !self.loaded else { return }
                self.output.append(data)
                guard let line = String(data: self.output, encoding: .utf8)?.split(separator: "\n").first,
                      let json = String(line).data(using: .utf8),
                      let object = try? JSONSerialization.jsonObject(with: json) as? [String: String],
                      let address = object["url"], let url = URL(string: address) else { return }
                self.loaded = true
                var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
                self.sessionToken = components.queryItems?.first(where: { $0.name == "token" })?.value ?? ""
                components.query = nil
                self.apiBase = components.url
                self.webView.load(URLRequest(url: url))
                self.refreshMenuState()
                self.stateTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in self?.refreshMenuState() }
            }
        }
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self, !self.terminating else { return }
                self.fail("The local monitor service stopped. Reopen Linewatch. Your measurements are retained in Application Support/Linewatch.")
            }
        }
        service = process
        do { try process.run() } catch { fail("Could not start the local monitor: \(error.localizedDescription)") }
    }

    func configureMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        let image = NSImage(size: NSSize(width: 18, height: 18), flipped: false) { _ in
            NSColor.black.setFill()
            for (x, height) in [(1, 4), (5, 7), (9, 10), (13, 14)] {
                NSBezierPath(roundedRect: NSRect(x: x, y: 2, width: 3, height: height), xRadius: 0.7, yRadius: 0.7).fill()
            }
            return true
        }
        image.isTemplate = true
        statusItem.button?.image = image
        statusItem.button?.setAccessibilityLabel("Linewatch broadband monitor")
        statusItem.button?.toolTip = "Linewatch — Broadband Monitor"
        statusMenu = NSMenu()
        statusMenu.autoenablesItems = false
        statusMenu.delegate = self
        monitorStateItem = NSMenuItem(title: "Connecting to monitor…", action: nil, keyEquivalent: "")
        speedItem = NSMenuItem(title: "Download average: loading…", action: nil, keyEquivalent: "")
        monitorStateItem.isEnabled = false
        speedItem.isEnabled = false
        statusMenu.addItem(monitorStateItem)
        statusMenu.addItem(speedItem)
        statusMenu.addItem(.separator())
        addItem("Open Dashboard", #selector(showDashboard), "o")
        runItem = addItem("Run Speed Test", #selector(runSpeedTest))
        reportItem = addItem("Open Latest Report", #selector(openReport))
        pauseItem = addItem("Pause Scheduled Tests", #selector(toggleSchedule))
        statusMenu.addItem(.separator())
        loginItem = addItem("Start at Login", #selector(toggleLogin))
        addItem("Login Item Settings…", #selector(openLoginSettings))
        statusMenu.addItem(.separator())
        let note = NSMenuItem(title: "Schedules run independently of this app", action: nil, keyEquivalent: "")
        note.isEnabled = false
        statusMenu.addItem(note)
        addItem("Quit Linewatch", #selector(NSApplication.terminate(_:)), "q").target = NSApp
        statusItem.menu = statusMenu
        runItem.isEnabled = false
        reportItem.isEnabled = false
        pauseItem.isEnabled = false
    }

    @discardableResult func addItem(_ title: String, _ action: Selector, _ shortcut: String = "") -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: shortcut)
        item.target = self
        statusMenu.addItem(item)
        return item
    }

    @objc func showDashboard() {
        NSApp.setActivationPolicy(.regular)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        sender.orderOut(nil)
        NSApp.setActivationPolicy(.accessory)
        return false
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showDashboard(); return true }

    func menuWillOpen(_ menu: NSMenu) { refreshMenuState() }

    func api(_ path: String, payload: [String: Any]? = nil, completion: @escaping (Result<[String: Any], Error>) -> Void) {
        guard let base = apiBase, let url = URL(string: "api/" + path, relativeTo: base) else { return }
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.setValue("linewatch=" + sessionToken, forHTTPHeaderField: "Cookie")
        if let payload = payload {
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("1", forHTTPHeaderField: "X-Linewatch")
            request.setValue(base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")), forHTTPHeaderField: "Origin")
            request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        }
        session.dataTask(with: request) { data, response, error in
            let result: Result<[String: Any], Error>
            if let error = error { result = .failure(error) }
            else if let data = data, let body = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let response = response as? HTTPURLResponse {
                if response.statusCode == 200 { result = .success(body) }
                else { result = .failure(NSError(domain: "Linewatch", code: response.statusCode, userInfo: [NSLocalizedDescriptionKey: body["error"] as? String ?? "The request failed."])) }
            } else { result = .failure(NSError(domain: "Linewatch", code: 1, userInfo: [NSLocalizedDescriptionKey: "The monitor did not return a valid response."])) }
            DispatchQueue.main.async { completion(result) }
        }.resume()
    }

    func refreshMenuState() {
        let loginStatus = SMAppService.mainApp.status
        loginItem.state = loginStatus == .enabled ? .on : .off
        loginItem.title = loginStatus == .requiresApproval ? "Start at Login (approval needed)" : "Start at Login"
        api("state") { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .success(let state):
                self.scheduled = state["schedule_enabled"] as? Bool ?? false
                let busy = state["busy"] as? Bool ?? false
                self.monitorStateItem.title = busy ? "Speed test in progress…" : self.scheduled ? "Scheduled monitoring is active" : "Scheduled monitoring is paused"
                let hours = ((state["config"] as? [String: Any])?["average_hours"] as? NSNumber)?.stringValue ?? "24"
                self.speedItem.title = (state["average_mbps"] as? Double).map { String(format: "%@h download average: %.1f Mbps", hours, $0) } ?? "Download average: no successful tests yet"
                self.pauseItem.title = self.scheduled ? "Pause Scheduled Tests" : "Resume Scheduled Tests"
                self.runItem.isEnabled = !busy && !self.commandInFlight
                self.reportItem.isEnabled = !busy && !self.commandInFlight
                self.pauseItem.isEnabled = !busy && !self.commandInFlight
                self.statusItem.button?.toolTip = self.monitorStateItem.title + "\n" + self.speedItem.title
            case .failure:
                self.monitorStateItem.title = "Monitor unavailable — reopen Linewatch"
                self.runItem.isEnabled = false; self.reportItem.isEnabled = false; self.pauseItem.isEnabled = false
            }
        }
    }

    func command(_ path: String, _ payload: [String: Any] = [:]) {
        commandInFlight = true
        runItem.isEnabled = false; reportItem.isEnabled = false; pauseItem.isEnabled = false
        api(path, payload: payload) { [weak self] result in
            guard let self = self else { return }
            self.commandInFlight = false
            if case .failure(let error) = result { self.fail(error.localizedDescription) }
            self.refreshMenuState()
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in self?.refreshMenuState() }
        }
    }

    @objc func runSpeedTest() { command("test") }
    @objc func openReport() { command("report") }
    @objc func toggleSchedule() { command("schedule", ["enabled": !scheduled]) }
    @objc func toggleLogin() {
        do {
            if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() }
            else if SMAppService.mainApp.status == .requiresApproval { SMAppService.openSystemSettingsLoginItems() }
            else { try SMAppService.mainApp.register() }
            refreshMenuState()
        } catch { fail("Could not change Start at Login: \(error.localizedDescription)") }
    }
    @objc func openLoginSettings() { SMAppService.openSystemSettingsLoginItems() }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "http", url.host == "127.0.0.1" { decisionHandler(.allow); return }
        if ["mailto", "https"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard smokeTest, webView.url?.path == "/", webView.url?.query == nil else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            self?.webView.evaluateJavaScript("document.querySelector('#plan').textContent !== '—' && document.querySelector('#email-form') !== null") { value, error in
                if let ok = value as? Bool, ok {
                    guard let self = self else { return }
                    self.window.performClose(nil)
                    guard !self.window.isVisible, self.statusItem.button != nil, self.service?.isRunning == true else { return self.fail("Closing the window did not preserve the menu bar monitor.") }
                    self.showDashboard()
                    guard self.window.isVisible else { return self.fail("Dashboard did not reopen from background mode.") }
                    self.api("state") { result in
                        if case .success = result { print("Native smoke test passed: dashboard, menu bar, close/reopen lifecycle and authenticated native API."); NSApp.terminate(nil) }
                        else { self.fail("Native menu API could not read monitor state.") }
                    }
                }
                else { self?.fail("Native smoke test failed: \(error?.localizedDescription ?? "dashboard data did not load")") }
            }
        }
    }

    func fail(_ message: String) { if smokeTest { fputs(message + "\n", stderr); service?.terminate(); exit(1) }; let alert = NSAlert(); alert.messageText = "Linewatch"; alert.informativeText = message; alert.runModal() }
    @objc func about() { NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "Linewatch", .applicationVersion: "1.1.0", .credits: NSAttributedString(string: "Broadband monitoring, on record.\nInter and JetBrains Mono fonts licensed under the SIL Open Font License.")]) }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationWillTerminate(_ notification: Notification) { terminating = true; stateTimer?.invalidate(); session.invalidateAndCancel(); if service?.isRunning == true { service?.terminate() } }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
