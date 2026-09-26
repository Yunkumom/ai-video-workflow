#!/usr/bin/swift

import AppKit
import Foundation

enum RenderError: Error, CustomStringConvertible {
    case missingArgument(String)
    case invalidNumber(String)
    case invalidTemplate(String)
    case imageEncoding

    var description: String {
        switch self {
        case .missingArgument(let name): return "Missing argument: \(name)"
        case .invalidNumber(let value): return "Invalid number: \(value)"
        case .invalidTemplate(let name): return "Unknown template: \(name)"
        case .imageEncoding: return "Could not encode frame PNG."
        }
    }
}

let validTemplates = [
    "gallery", "clean-impact", "keyword-punch", "split-reveal",
    "flash-cut", "punch-zoom", "freeze-hit",
]

func argumentValue(_ name: String, arguments: [String]) throws -> String {
    guard let index = arguments.firstIndex(of: name), arguments.indices.contains(index + 1) else {
        throw RenderError.missingArgument(name)
    }
    return arguments[index + 1]
}

func clamp(_ value: Double, _ minimum: Double = 0, _ maximum: Double = 1) -> Double {
    return min(maximum, max(minimum, value))
}

func easeOutBack(_ value: Double) -> Double {
    let x = clamp(value) - 1
    let c1 = 1.70158
    let c3 = c1 + 1
    return 1 + c3 * x * x * x + c1 * x * x
}

func pulse(_ value: Double) -> Double {
    return sin(clamp(value) * .pi)
}

func primaryFont(size: CGFloat, heavy: Bool = true) -> NSFont {
    if heavy {
        return NSFont.systemFont(ofSize: size, weight: .black)
    }
    let names = heavy
        ? ["PingFangTC-Semibold", "NotoSansCJKtc-Black", "Arial-BoldMT"]
        : ["PingFangTC-Regular", "NotoSansCJKtc-Regular", "ArialMT"]
    for name in names {
        if let font = NSFont(name: name, size: size) { return font }
    }
    return NSFont.systemFont(ofSize: size, weight: heavy ? .black : .regular)
}

func roundedRect(_ rect: NSRect, radius: CGFloat, color: NSColor) {
    color.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
}

func line(_ start: NSPoint, _ end: NSPoint, width: CGFloat, color: NSColor) {
    let path = NSBezierPath()
    path.move(to: start)
    path.line(to: end)
    path.lineWidth = width
    color.setStroke()
    path.stroke()
}

func textAttributes(size: CGFloat, color: NSColor, outline: NSColor, heavy: Bool = true) -> [NSAttributedString.Key: Any] {
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = .center
    paragraph.lineBreakMode = .byCharWrapping
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.35)
    shadow.shadowBlurRadius = 5
    shadow.shadowOffset = NSSize(width: 0, height: -3)
    return [
        .font: primaryFont(size: size, heavy: heavy),
        .foregroundColor: color,
        .strokeColor: outline,
        .strokeWidth: heavy ? -3.0 : -2.0,
        .paragraphStyle: paragraph,
        .shadow: shadow,
    ]
}

@discardableResult
func drawText(
    _ text: String,
    center: NSPoint,
    width: CGFloat,
    size: CGFloat,
    color: NSColor,
    outline: NSColor,
    scale: CGFloat = 1,
    heavy: Bool = true
) -> NSRect {
    let finalSize = size * scale
    let attributed = NSAttributedString(
        string: text,
        attributes: textAttributes(size: finalSize, color: color, outline: outline, heavy: heavy)
    )
    let measured = attributed.boundingRect(
        with: NSSize(width: width, height: 500),
        options: [.usesLineFragmentOrigin, .usesFontLeading]
    )
    let rect = NSRect(
        x: center.x - width / 2,
        y: center.y - ceil(measured.height) / 2,
        width: width,
        height: ceil(measured.height) + 8
    )
    attributed.draw(with: rect, options: [.usesLineFragmentOrigin, .usesFontLeading])
    return rect
}

func drawClippedText(
    _ text: String,
    center: NSPoint,
    width: CGFloat,
    size: CGFloat,
    color: NSColor,
    outline: NSColor,
    upperHalf: Bool,
    offset: CGFloat
) {
    let attributed = NSAttributedString(
        string: text,
        attributes: textAttributes(size: size, color: color, outline: outline)
    )
    let measured = attributed.boundingRect(
        with: NSSize(width: width, height: 300),
        options: [.usesLineFragmentOrigin, .usesFontLeading]
    )
    var rect = NSRect(
        x: center.x - width / 2,
        y: center.y - ceil(measured.height) / 2,
        width: width,
        height: ceil(measured.height) + 8
    )
    rect.origin.y += upperHalf ? offset : -offset
    let clip = upperHalf
        ? NSRect(x: rect.minX, y: rect.midY, width: rect.width, height: rect.height / 2 + 8)
        : NSRect(x: rect.minX, y: rect.minY, width: rect.width, height: rect.height / 2 + 8)
    NSGraphicsContext.saveGraphicsState()
    NSBezierPath(rect: clip).addClip()
    attributed.draw(with: rect, options: [.usesLineFragmentOrigin, .usesFontLeading])
    NSGraphicsContext.restoreGraphicsState()
}

func transitionFlash(_ localTime: Double) -> CGFloat {
    if localTime < 0 || localTime > 0.10 { return 0 }
    return CGFloat(1 - localTime / 0.10)
}

func drawBackdrop(width: CGFloat, height: CGFloat, light: Bool, progress: Double) {
    (light ? NSColor(calibratedWhite: 0.94, alpha: 1) : NSColor(calibratedWhite: 0.025, alpha: 1)).setFill()
    NSRect(x: 0, y: 0, width: width, height: height).fill()
    let ink = light ? NSColor.black.withAlphaComponent(0.08) : NSColor.white.withAlphaComponent(0.07)
    for index in 0..<7 {
        let shift = CGFloat((progress * 120).truncatingRemainder(dividingBy: 120))
        line(
            NSPoint(x: CGFloat(index) * 100 - 100 + shift, y: 0),
            NSPoint(x: CGFloat(index) * 100 + 160 + shift, y: height),
            width: 2,
            color: ink
        )
    }
}

func drawSceneLabel(_ category: String, _ identifier: String, width: CGFloat) {
    roundedRect(NSRect(x: 36, y: 42, width: width - 72, height: 58), radius: 29, color: NSColor.black.withAlphaComponent(0.86))
    drawText(
        "\(category)  ·  \(identifier)",
        center: NSPoint(x: width / 2, y: 70),
        width: width - 100,
        size: 20,
        color: .white,
        outline: .black,
        heavy: false
    )
}

func drawHeader(_ title: String, width: CGFloat, light: Bool = false) {
    drawText(
        title,
        center: NSPoint(x: width / 2, y: 858),
        width: width - 72,
        size: 22,
        color: light ? .black : .white,
        outline: light ? .white : .black,
        heavy: false
    )
}

func drawCleanImpact(_ progress: Double, width: CGFloat, height: CGFloat) {
    drawBackdrop(width: width, height: height, light: false, progress: progress)
    drawHeader("01  乾淨重擊", width: width)
    let entrance = CGFloat(easeOutBack(clamp(progress / 0.36)))
    drawText(
        "一句話\n乾淨落地",
        center: NSPoint(x: width / 2, y: 505),
        width: width - 80,
        size: 64,
        color: .white,
        outline: .black,
        scale: 0.65 + entrance * 0.35
    )
    drawSceneLabel("字幕模板", "clean-impact", width: width)
}

func drawKeywordPunch(_ progress: Double, width: CGFloat, height: CGFloat) {
    drawBackdrop(width: width, height: height, light: true, progress: progress)
    drawHeader("02  關鍵字跳出", width: width, light: true)
    drawText(
        "讓重點自己",
        center: NSPoint(x: width / 2, y: 575),
        width: width - 80,
        size: 48,
        color: .black,
        outline: .white
    )
    let reveal = clamp((progress - 0.32) / 0.28)
    if reveal > 0 {
        let scale = CGFloat(0.55 + 0.45 * easeOutBack(reveal))
        drawText(
            "跳出來",
            center: NSPoint(x: width / 2, y: 475),
            width: width - 70,
            size: 78,
            color: NSColor.systemYellow,
            outline: .black,
            scale: scale
        )
    }
    drawSceneLabel("字幕模板", "keyword-punch", width: width)
}

func drawSplitReveal(_ progress: Double, width: CGFloat, height: CGFloat) {
    drawBackdrop(width: width, height: height, light: false, progress: progress)
    drawHeader("03  黃字裂開補白", width: width)
    let center = NSPoint(x: width / 2, y: 510)
    let split = clamp((progress - 0.38) / 0.24)
    if split <= 0 {
        drawText(
            "那種無助",
            center: center,
            width: width - 56,
            size: 80,
            color: NSColor.systemYellow,
            outline: .black,
            scale: CGFloat(0.8 + 0.2 * easeOutBack(clamp(progress / 0.30)))
        )
    } else {
        let distance = CGFloat(7 + 22 * split)
        drawClippedText(
            "那種無助",
            center: center,
            width: width - 56,
            size: 80,
            color: NSColor.systemYellow,
            outline: .black,
            upperHalf: true,
            offset: distance
        )
        drawClippedText(
            "那種無助",
            center: center,
            width: width - 56,
            size: 80,
            color: NSColor.systemYellow,
            outline: .black,
            upperHalf: false,
            offset: distance
        )
        drawText(
            "崩潰大哭",
            center: center,
            width: width - 72,
            size: 86,
            color: .white,
            outline: .black,
            scale: CGFloat(0.55 + 0.45 * easeOutBack(split))
        )
    }
    drawSceneLabel("字幕模板", "split-reveal", width: width)
}

func drawFlashCut(_ progress: Double, width: CGFloat, height: CGFloat) {
    let flash = progress > 0.38 && progress < 0.48
    drawBackdrop(width: width, height: height, light: flash, progress: progress)
    drawHeader("04  黑白閃切", width: width, light: flash)
    let label = progress < 0.43 ? "BLACK" : "閃白 → CUT"
    drawText(
        label,
        center: NSPoint(x: width / 2, y: 510),
        width: width - 60,
        size: 62,
        color: flash ? .black : .white,
        outline: flash ? .white : .black,
        scale: CGFloat(0.95 + pulse(progress) * 0.08)
    )
    drawSceneLabel("剪輯模板", "flash-cut", width: width)
}

func drawPunchZoom(_ progress: Double, width: CGFloat, height: CGFloat) {
    drawBackdrop(width: width, height: height, light: false, progress: progress)
    drawHeader("05  重點推近", width: width)
    let zoomProgress = clamp((progress - 0.18) / 0.42)
    let scale = CGFloat(0.60 + 0.40 * easeOutBack(zoomProgress))
    for index in 0..<3 {
        let inset = CGFloat(90 - index * 18) * scale
        let rect = NSRect(x: inset, y: 300 + inset / 2, width: width - inset * 2, height: 370 - inset)
        let path = NSBezierPath(roundedRect: rect, xRadius: 28, yRadius: 28)
        path.lineWidth = CGFloat(2 + index)
        NSColor.systemYellow.withAlphaComponent(0.24 + CGFloat(index) * 0.14).setStroke()
        path.stroke()
    }
    drawText(
        "重點\n靠近",
        center: NSPoint(x: width / 2, y: 510),
        width: width - 100,
        size: 76,
        color: .white,
        outline: .black,
        scale: scale
    )
    drawSceneLabel("剪輯模板", "punch-zoom", width: width)
}

func drawFreezeHit(_ progress: Double, width: CGFloat, height: CGFloat) {
    drawBackdrop(width: width, height: height, light: true, progress: progress)
    drawHeader("06  定格重擊", width: width, light: true)
    let travel = clamp(progress / 0.52)
    let x = CGFloat(85 + 350 * travel)
    NSColor.black.setFill()
    NSBezierPath(ovalIn: NSRect(x: x - 34, y: 480, width: 68, height: 68)).fill()
    if progress >= 0.52 {
        let frame = NSRect(x: x - 76, y: 438, width: 152, height: 152)
        let path = NSBezierPath(rect: frame)
        path.lineWidth = 8
        NSColor.systemYellow.setStroke()
        path.stroke()
        drawText(
            "FREEZE",
            center: NSPoint(x: width / 2, y: 380),
            width: width - 80,
            size: 58,
            color: .black,
            outline: .white,
            scale: CGFloat(0.7 + 0.3 * easeOutBack(clamp((progress - 0.52) / 0.25)))
        )
    }
    drawSceneLabel("剪輯模板", "freeze-hit", width: width)
}

func drawIntro(_ progress: Double, width: CGFloat, height: CGFloat) {
    let light = progress < 0.10 || (progress > 0.43 && progress < 0.50)
    drawBackdrop(width: width, height: height, light: light, progress: progress)
    drawText(
        "SHINE",
        center: NSPoint(x: width / 2, y: 620),
        width: width - 80,
        size: 86,
        color: light ? .black : .white,
        outline: light ? .white : .black,
        scale: CGFloat(0.72 + 0.28 * easeOutBack(clamp(progress / 0.30)))
    )
    drawText(
        "字幕 × 剪輯\nTEMPLATE GALLERY",
        center: NSPoint(x: width / 2, y: 455),
        width: width - 80,
        size: 38,
        color: NSColor.systemYellow,
        outline: .black
    )
    roundedRect(NSRect(x: 115, y: 220, width: width - 230, height: 8), radius: 4, color: light ? .black : .white)
}

func drawOutro(_ progress: Double, width: CGFloat, height: CGFloat) {
    drawBackdrop(width: width, height: height, light: false, progress: progress)
    drawText(
        "看懂風格\n再套用模板",
        center: NSPoint(x: width / 2, y: 545),
        width: width - 70,
        size: 60,
        color: .white,
        outline: .black,
        scale: CGFloat(0.82 + 0.18 * easeOutBack(clamp(progress / 0.35)))
    )
    drawText(
        "3 字幕風格  +  3 剪輯風格",
        center: NSPoint(x: width / 2, y: 355),
        width: width - 70,
        size: 26,
        color: NSColor.systemYellow,
        outline: .black,
        heavy: false
    )
}

func drawIndividual(_ template: String, progress: Double, width: CGFloat, height: CGFloat) {
    switch template {
    case "clean-impact": drawCleanImpact(progress, width: width, height: height)
    case "keyword-punch": drawKeywordPunch(progress, width: width, height: height)
    case "split-reveal": drawSplitReveal(progress, width: width, height: height)
    case "flash-cut": drawFlashCut(progress, width: width, height: height)
    case "punch-zoom": drawPunchZoom(progress, width: width, height: height)
    case "freeze-hit": drawFreezeHit(progress, width: width, height: height)
    default: break
    }
}

func drawGallery(time: Double, width: CGFloat, height: CGFloat) {
    let scenes: [(start: Double, end: Double, name: String)] = [
        (0.0, 2.5, "intro"),
        (2.5, 5.5, "clean-impact"),
        (5.5, 8.5, "keyword-punch"),
        (8.5, 12.5, "split-reveal"),
        (12.5, 15.0, "flash-cut"),
        (15.0, 17.8, "punch-zoom"),
        (17.8, 20.3, "freeze-hit"),
        (20.3, 22.5, "outro"),
    ]
    guard let scene = scenes.first(where: { time >= $0.start && time < $0.end }) ?? scenes.last else { return }
    let localTime = time - scene.start
    let progress = clamp(localTime / (scene.end - scene.start))
    switch scene.name {
    case "intro": drawIntro(progress, width: width, height: height)
    case "outro": drawOutro(progress, width: width, height: height)
    default: drawIndividual(scene.name, progress: progress, width: width, height: height)
    }
    let flashAlpha = transitionFlash(localTime)
    if scene.start > 0, flashAlpha > 0 {
        NSColor.white.withAlphaComponent(flashAlpha).setFill()
        NSRect(x: 0, y: 0, width: width, height: height).fill()
    }
}

func writeFrame(
    template: String,
    time: Double,
    output: URL,
    width: Int,
    height: Int,
    duration: Double
) throws {
    guard let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: width,
        pixelsHigh: height,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ), let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        throw RenderError.imageEncoding
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.shouldAntialias = true
    let canvasWidth = CGFloat(width)
    let canvasHeight = CGFloat(height)
    if template == "gallery" {
        drawGallery(time: time, width: canvasWidth, height: canvasHeight)
    } else {
        drawIndividual(template, progress: clamp(time / duration), width: canvasWidth, height: canvasHeight)
        let flashAlpha = transitionFlash(time)
        if flashAlpha > 0 {
            NSColor.white.withAlphaComponent(flashAlpha).setFill()
            NSRect(x: 0, y: 0, width: canvasWidth, height: canvasHeight).fill()
        }
    }
    context.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()
    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        throw RenderError.imageEncoding
    }
    try png.write(to: output, options: .atomic)
}

do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    let template = try argumentValue("--template", arguments: arguments)
    guard validTemplates.contains(template) else { throw RenderError.invalidTemplate(template) }
    let outputDirectory = URL(fileURLWithPath: try argumentValue("--output-dir", arguments: arguments))
    guard let width = Int(try argumentValue("--width", arguments: arguments)), width > 0 else {
        throw RenderError.invalidNumber("width")
    }
    guard let height = Int(try argumentValue("--height", arguments: arguments)), height > 0 else {
        throw RenderError.invalidNumber("height")
    }
    guard let fps = Int(try argumentValue("--fps", arguments: arguments)), fps > 0 else {
        throw RenderError.invalidNumber("fps")
    }
    let duration = template == "gallery" ? 22.5 : 4.0
    let frameCount = Int(ceil(duration * Double(fps)))
    try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
    for frame in 0..<frameCount {
        let name = String(format: "frame-%05d.png", frame + 1)
        try writeFrame(
            template: template,
            time: Double(frame) / Double(fps),
            output: outputDirectory.appendingPathComponent(name),
            width: width,
            height: height,
            duration: duration
        )
    }
} catch {
    FileHandle.standardError.write(Data("[ERROR] \(error)\n".utf8))
    exit(2)
}
