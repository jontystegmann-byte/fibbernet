import AppKit

@main
struct IconGenerator {
    static func main() throws {
let size: CGFloat = 1024
let image = NSImage(size: NSSize(width: size, height: size))
image.lockFocus()
let tile = NSBezierPath(roundedRect: NSRect(x: 62, y: 62, width: 900, height: 900), xRadius: 200, yRadius: 200)
let gradient = NSGradient(starting: NSColor(srgbRed: 0.93, green: 0.17, blue: 0.22, alpha: 1), ending: NSColor(srgbRed: 0.78, green: 0.07, blue: 0.12, alpha: 1))!
gradient.draw(in: tile, angle: -90)
NSColor.white.setFill()
FibberMark.path(in: NSRect(x: 190, y: 190, width: 644, height: 644)).fill()
image.unlockFocus()
let data = NSBitmapImageRep(data: image.tiffRepresentation!)!.representation(using: .png, properties: [:])!
try data.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
    }
}
