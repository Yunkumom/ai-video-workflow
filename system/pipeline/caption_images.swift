#!/usr/bin/env swift

import AppKit
import Foundation

struct Cue: Decodable {
    let text: String
    let start: Double
    let end: Double
}

struct CaptionLineLayout {
    let attributed: NSAttributedString
    let backgroundRect: NSRect
    let textRect: NSRect
}

enum CaptionError: Error, CustomStringConvertible {
    case usage
    case imageEncoding

    var description: String {
        switch self {
        case .usage:
            return "Usage: caption_images.swift --input <json> --output-dir <dir> --video-width <pixels>"
        case .imageEncoding:
            return "Could not encode a caption PNG."
        }
    }
}

func argumentValue(_ name: String, in arguments: [String]) throws -> String {
    guard let index = arguments.firstIndex(of: name), arguments.indices.contains(index + 1) else {
        throw CaptionError.usage
    }
    return arguments[index + 1]
}

func styledCaption(_ text: String, baseFontSize: Double, paragraph: NSParagraphStyle, darkText: Bool, outlined: Bool, heavyText: Bool) -> NSAttributedString {
    let regularFont = NSFont(name: "Noto Sans CJK TC", size: baseFontSize)
        ?? NSFont(name: "Source Han Sans TC", size: baseFontSize)
        ?? NSFont(name: "PingFang TC", size: baseFontSize)
        ?? NSFont.systemFont(ofSize: baseFontSize, weight: .regular)
    let boldFont = NSFont(name: "Noto Sans CJK TC Bold", size: baseFontSize * 1.08)
        ?? NSFont(name: "Source Han Sans TC Bold", size: baseFontSize * 1.08)
        ?? NSFontManager.shared.convert(regularFont, toHaveTrait: .boldFontMask)
    let primaryFont = heavyText ? boldFont : regularFont
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.9)
    shadow.shadowBlurRadius = 5
    shadow.shadowOffset = NSSize(width: 0, height: -2)
    let textColor = darkText ? NSColor.black : NSColor.white
    var regularAttributes: [NSAttributedString.Key: Any] = [
        .font: primaryFont,
        .foregroundColor: textColor,
        .paragraphStyle: paragraph,
        .shadow: shadow,
    ]
    var boldAttributes: [NSAttributedString.Key: Any] = [
        .font: boldFont,
        .foregroundColor: textColor,
        .paragraphStyle: paragraph,
        .shadow: shadow,
    ]
    if darkText {
        regularAttributes[.strokeColor] = NSColor.white
        regularAttributes[.strokeWidth] = 3.0
        boldAttributes[.strokeColor] = NSColor.white
        boldAttributes[.strokeWidth] = 3.0
    }
    if outlined {
        regularAttributes[.strokeColor] = NSColor(calibratedWhite: 0.08, alpha: 0.95)
        regularAttributes[.strokeWidth] = -2.5
        boldAttributes[.strokeColor] = NSColor(calibratedWhite: 0.08, alpha: 0.95)
        boldAttributes[.strokeWidth] = -2.5
    }
    let result = NSMutableAttributedString()
    var remaining = text
    while let boldStart = remaining.range(of: "{\\b1}") {
        result.append(NSAttributedString(string: String(remaining[..<boldStart.lowerBound]), attributes: regularAttributes))
        remaining = String(remaining[boldStart.upperBound...])
        if let boldEnd = remaining.range(of: "{\\b0}") {
            result.append(NSAttributedString(string: String(remaining[..<boldEnd.lowerBound]), attributes: boldAttributes))
            remaining = String(remaining[boldEnd.upperBound...])
        } else {
            result.append(NSAttributedString(string: remaining, attributes: boldAttributes))
            remaining = ""
            break
        }
    }
    if !remaining.isEmpty {
        result.append(NSAttributedString(string: remaining, attributes: regularAttributes))
    }
    return result
}

func fittedLineLayouts(_ text: String, canvasWidth: Int, canvasHeight: Int, fontSize: Double, darkText: Bool, outlined: Bool, heavyText: Bool) -> [CaptionLineLayout] {
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = .center
    paragraph.lineBreakMode = .byClipping
    let sourceLines = text.split(separator: "\n", omittingEmptySubsequences: false).prefix(2)
    let attributedLines = sourceLines.map {
        styledCaption(String($0), baseFontSize: fontSize, paragraph: paragraph, darkText: darkText, outlined: outlined, heavyText: heavyText)
    }
    let measured = attributedLines.map {
        $0.boundingRect(
            with: NSSize(width: canvasWidth - 48, height: Int(fontSize * 2.0)),
            options: [.usesLineFragmentOrigin, .usesFontLeading]
        )
    }
    let backgroundHeights = measured.map { max(ceil($0.height) + 16, fontSize * 1.32) }
    let gap = fontSize * 0.14
    let totalHeight = backgroundHeights.reduce(0, +) + gap * Double(max(0, backgroundHeights.count - 1))
    var top = (Double(canvasHeight) + totalHeight) / 2.0
    var layouts: [CaptionLineLayout] = []
    for (index, attributed) in attributedLines.enumerated() {
        let backgroundHeight = backgroundHeights[index]
        top -= backgroundHeight
        let backgroundWidth = min(Double(canvasWidth - 16), ceil(measured[index].width) + 28)
        let backgroundRect = NSRect(
            x: (Double(canvasWidth) - backgroundWidth) / 2.0,
            y: top,
            width: backgroundWidth,
            height: backgroundHeight
        )
        let textRect = NSRect(
            x: backgroundRect.minX + 14,
            y: backgroundRect.minY + 8,
            width: backgroundRect.width - 28,
            height: backgroundRect.height - 16
        )
        layouts.append(
            CaptionLineLayout(
                attributed: attributed,
                backgroundRect: backgroundRect,
                textRect: textRect
            )
        )
        top -= gap
    }
    return layouts
}

func writePNG(text: String?, to url: URL, width: Int, showBackground: Bool, fontScale: Double, darkText: Bool, outlined: Bool, fitBackground: Bool, heavyText: Bool) throws {
    let canvasWidth = max(160, min(width - 40, 1600))
    let adaptiveMinimum = min(42.0, Double(width) * 0.045)
    let fontSize = max(
        24.0,
        min(144.0, max(adaptiveMinimum, Double(width) * 0.019 * fontScale))
    )
    // Keep every timeline PNG at one geometry so FFmpeg can hold each caption
    // frame between cue boundaries without reinitializing the overlay graph.
    let canvasHeight = Int(max(92.0, fontSize * (fitBackground ? 3.4 : 5.2)))
    guard let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: canvasWidth,
        pixelsHigh: canvasHeight,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ), let graphicsContext = NSGraphicsContext(bitmapImageRep: bitmap) else {
        throw CaptionError.imageEncoding
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = graphicsContext
    NSColor.clear.setFill()
    NSRect(x: 0, y: 0, width: canvasWidth, height: canvasHeight).fill()

    if let text, !text.isEmpty {
        if fitBackground {
            let layouts = fittedLineLayouts(
                text,
                canvasWidth: canvasWidth,
                canvasHeight: canvasHeight,
                fontSize: fontSize,
                darkText: darkText,
                outlined: outlined,
                heavyText: heavyText
            )
            for layout in layouts {
                if showBackground {
                    let background = NSBezierPath(
                        roundedRect: layout.backgroundRect,
                        xRadius: 12,
                        yRadius: 12
                    )
                    NSColor(calibratedWhite: 0.0, alpha: 0.82).setFill()
                    background.fill()
                }
                let attributed = layout.attributed
                attributed.draw(
                    with: layout.textRect,
                    options: [.usesLineFragmentOrigin, .usesFontLeading],
                    context: nil
                )
            }
        } else {
            let paragraph = NSMutableParagraphStyle()
            paragraph.alignment = .center
            paragraph.lineBreakMode = .byCharWrapping
            let attributed = styledCaption(text, baseFontSize: fontSize, paragraph: paragraph, darkText: darkText, outlined: outlined, heavyText: heavyText)
            let backgroundRect = NSRect(x: 8, y: 8, width: canvasWidth - 16, height: canvasHeight - 16)
            if showBackground {
                let background = NSBezierPath(roundedRect: backgroundRect, xRadius: 12, yRadius: 12)
                NSColor(calibratedWhite: 0.0, alpha: 0.82).setFill()
                background.fill()
            }
            attributed.draw(
                with: NSRect(x: 24, y: 16, width: canvasWidth - 48, height: canvasHeight - 32),
                options: [.usesLineFragmentOrigin, .usesFontLeading],
                context: nil
            )
        }
    }
    graphicsContext.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()

    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        throw CaptionError.imageEncoding
    }
    try png.write(to: url, options: .atomic)
}

do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    let input = URL(fileURLWithPath: try argumentValue("--input", in: arguments))
    let outputDirectory = URL(fileURLWithPath: try argumentValue("--output-dir", in: arguments))
    guard let videoWidth = Int(try argumentValue("--video-width", in: arguments)) else {
        throw CaptionError.usage
    }
    let cues = try JSONDecoder().decode([Cue].self, from: Data(contentsOf: input))
    try FileManager.default.createDirectory(
        at: outputDirectory,
        withIntermediateDirectories: true
    )
    let showBackground = !arguments.contains("--plain")
    let darkText = arguments.contains("--dark-text")
    let outlined = arguments.contains("--outline")
    let fitBackground = arguments.contains("--fit-background")
    let heavyText = arguments.contains("--heavy-text")
    let fontScale = Double((try? argumentValue("--font-scale", in: arguments)) ?? "1.0") ?? 1.0
    try writePNG(text: nil, to: outputDirectory.appendingPathComponent("blank.png"), width: videoWidth, showBackground: showBackground, fontScale: fontScale, darkText: darkText, outlined: outlined, fitBackground: fitBackground, heavyText: heavyText)
    for (index, cue) in cues.enumerated() {
        let name = String(format: "caption-%04d.png", index + 1)
        try writePNG(
            text: cue.text,
            to: outputDirectory.appendingPathComponent(name),
            width: videoWidth,
            showBackground: showBackground,
            fontScale: fontScale,
            darkText: darkText,
            outlined: outlined,
            fitBackground: fitBackground,
            heavyText: heavyText
        )
    }
} catch {
    FileHandle.standardError.write(Data("[ERROR] \(error)\n".utf8))
    exit(2)
}
