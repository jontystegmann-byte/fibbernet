import AppKit
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var service: Process?
    var output = Data()
    var terminating = false
    var loaded = false
    let smokeTest = CommandLine.arguments.contains("--smoke-test")

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

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1260, height: 850), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Linewatch — Broadband Monitor"
        window.minSize = NSSize(width: 820, height: 620)
        window.center()
        window.delegate = self
        webView = WKWebView(frame: .zero)
        webView.navigationDelegate = self
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
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
                self.webView.load(URLRequest(url: url))
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
                if let ok = value as? Bool, ok { print("Native WebKit smoke test passed: app UI and authenticated bundled engine."); NSApp.terminate(nil) }
                else { self?.fail("Native smoke test failed: \(error?.localizedDescription ?? "dashboard data did not load")") }
            }
        }
    }

    func fail(_ message: String) { if smokeTest { fputs(message + "\n", stderr); service?.terminate(); exit(1) }; let alert = NSAlert(); alert.messageText = "Linewatch"; alert.informativeText = message; alert.runModal() }
    @objc func about() { NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "Linewatch", .applicationVersion: "1.0.1", .credits: NSAttributedString(string: "Broadband monitoring, on record.\nInter and JetBrains Mono fonts licensed under the SIL Open Font License.")]) }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { terminating = true; if service?.isRunning == true { service?.terminate() } }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
