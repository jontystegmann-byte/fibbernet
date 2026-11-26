import AppKit

// One vector mark for the app, dashboard and monochrome menu bar icon.
// A talking profile with an exaggerated nose and one eye punched out.
enum FibberMark {
    static func path(in rect: NSRect) -> NSBezierPath {
        let p = NSBezierPath()
        p.move(to: NSPoint(x: 5, y: 5.5))
        p.curve(to: NSPoint(x: 1.5, y: 12.5), controlPoint1: NSPoint(x: 2.5, y: 7), controlPoint2: NSPoint(x: 1.5, y: 9))
        p.curve(to: NSPoint(x: 8.5, y: 21.5), controlPoint1: NSPoint(x: 1.5, y: 18), controlPoint2: NSPoint(x: 4, y: 21.5))
        p.curve(to: NSPoint(x: 14.5, y: 15.5), controlPoint1: NSPoint(x: 12.5, y: 21.5), controlPoint2: NSPoint(x: 14.5, y: 19))
        p.line(to: NSPoint(x: 23, y: 14))
        p.line(to: NSPoint(x: 23, y: 11.5))
        p.line(to: NSPoint(x: 14.5, y: 11.5))
        p.curve(to: NSPoint(x: 8.5, y: 5.5), controlPoint1: NSPoint(x: 14.5, y: 7.5), controlPoint2: NSPoint(x: 12.5, y: 5.5))
        p.line(to: NSPoint(x: 4, y: 2))
        p.line(to: NSPoint(x: 5, y: 5.5))
        p.close()
        p.appendOval(in: NSRect(x: 9, y: 15.2, width: 2.8, height: 2.8))
        p.windingRule = .evenOdd
        var transform = AffineTransform()
        transform.translate(x: rect.minX, y: rect.minY)
        transform.scale(x: rect.width / 24, y: rect.height / 24)
        p.transform(using: transform)
        return p
    }
}
