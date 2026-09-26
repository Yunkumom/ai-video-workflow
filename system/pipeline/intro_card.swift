import Foundation
import Cocoa
import CoreGraphics
import CoreText

// Command line argument parser helper
func getArg(_ flag: String, default defaultValue: String = "") -> String {
    let args = CommandLine.arguments
    if let idx = args.firstIndex(of: flag), idx + 1 < args.count {
        return args[idx + 1]
    }
    return defaultValue
}

let inputPath = getArg("--input")
let outputPath = getArg("--output")
let title = getArg("--title", default: "TITLE")
let subtitle = getArg("--subtitle", default: "")
let category = getArg("--category", default: "")
let orientation = getArg("--orientation", default: "vertical")

guard !inputPath.isEmpty, !outputPath.isEmpty else {
    print("Usage: swift intro_card.swift --input <image> --output <png> --title <title> [--subtitle <subt>] [--category <cat>] [--orientation <vertical|horizontal>]")
    exit(1)
}

let isVertical = (orientation.lowercased() != "horizontal")
let targetW: CGFloat = isVertical ? 1080 : 1920
let targetH: CGFloat = isVertical ? 1920 : 1080

guard let inputImage = NSImage(contentsOfFile: inputPath),
      let tiffData = inputImage.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiffData),
      let cgInput = bitmap.cgImage else {
    print("Failed to load input image: \(inputPath)")
    exit(1)
}

let colorSpace = CGColorSpaceCreateDeviceRGB()
guard let ctx = CGContext(
    data: nil,
    width: Int(targetW),
    height: Int(targetH),
    bitsPerComponent: 8,
    bytesPerRow: 0,
    space: colorSpace,
    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
) else {
    print("Failed to create CGContext")
    exit(1)
}

// 1. Draw input image (aspect fill with center crop)
let inW = CGFloat(cgInput.width)
let inH = CGFloat(cgInput.height)
let scale = max(targetW / inW, targetH / inH)
let drawW = inW * scale
let drawH = inH * scale
let drawX = (targetW - drawW) / 2.0
let drawY = (targetH - drawH) / 2.0

ctx.draw(cgInput, in: CGRect(x: drawX, y: drawY, width: drawW, height: drawH))

// 2. Cinematic top & bottom atmospheric gradients
let colors = [
    NSColor(red: 0, green: 0, blue: 0, alpha: 0.68).cgColor,
    NSColor(red: 0, green: 0, blue: 0, alpha: 0.0).cgColor
] as CFArray
let locations: [CGFloat] = [0.0, 1.0]

if let gradient = CGGradient(colorsSpace: colorSpace, colors: colors, locations: locations) {
    let topFadeH: CGFloat = isVertical ? 460 : 280
    let bottomFadeH: CGFloat = isVertical ? 580 : 360

    // Top subtle gradient
    ctx.drawLinearGradient(
        gradient,
        start: CGPoint(x: targetW / 2, y: targetH),
        end: CGPoint(x: targetW / 2, y: targetH - topFadeH),
        options: []
    )
    // Bottom subtle gradient for typography readability
    ctx.drawLinearGradient(
        gradient,
        start: CGPoint(x: targetW / 2, y: 0),
        end: CGPoint(x: targetW / 2, y: bottomFadeH),
        options: []
    )
}

// 3. Category Pill / Badge at top
if !category.isEmpty {
    let badgeFontSize: CGFloat = isVertical ? 32 : 28
    let badgeFont = NSFont.systemFont(ofSize: badgeFontSize, weight: .bold)
    let badgeAttrs: [NSAttributedString.Key: Any] = [
        .font: badgeFont,
        .foregroundColor: NSColor.white
    ]
    let badgeStr = NSAttributedString(string: category.uppercased(), attributes: badgeAttrs)
    let badgeLine = CTLineCreateWithAttributedString(badgeStr)
    let badgeBounds = CTLineGetBoundsWithOptions(badgeLine, .useGlyphPathBounds)
    let badgePadX: CGFloat = isVertical ? 34 : 28
    let badgePadY: CGFloat = isVertical ? 14 : 12
    let badgeY: CGFloat = isVertical ? targetH - 220 : targetH - 140
    let badgeRect = CGRect(
        x: (targetW - (badgeBounds.width + badgePadX * 2)) / 2,
        y: badgeY,
        width: badgeBounds.width + badgePadX * 2,
        height: badgeBounds.height + badgePadY * 2
    )

    ctx.saveGState()
    let cornerR: CGFloat = (badgeBounds.height + badgePadY * 2) / 2.0
    let path = CGPath(roundedRect: badgeRect, cornerWidth: cornerR, cornerHeight: cornerR, transform: nil)
    ctx.addPath(path)
    ctx.setFillColor(NSColor(red: 0.95, green: 0.35, blue: 0.15, alpha: 0.92).cgColor) // Warm vivid accent
    ctx.fillPath()
    ctx.restoreGState()

    ctx.saveGState()
    ctx.textPosition = CGPoint(
        x: badgeRect.origin.x + badgePadX - badgeBounds.origin.x,
        y: badgeRect.origin.y + badgePadY - badgeBounds.origin.y
    )
    CTLineDraw(badgeLine, ctx)
    ctx.restoreGState()
}

// Shadow setup
let titleShadow = NSShadow()
titleShadow.shadowColor = NSColor.black.withAlphaComponent(0.85)
titleShadow.shadowOffset = CGSize(width: 0, height: -4)
titleShadow.shadowBlurRadius = 14

// 4. Main Title
let titleFontSize: CGFloat = isVertical ? 82 : 72
let titleFont = NSFont.systemFont(ofSize: titleFontSize, weight: .black)
let titleAttrs: [NSAttributedString.Key: Any] = [
    .font: titleFont,
    .foregroundColor: NSColor.white,
    .shadow: titleShadow
]
let titleStr = NSAttributedString(string: title, attributes: titleAttrs)
let titleLine = CTLineCreateWithAttributedString(titleStr)
let titleBounds = CTLineGetBoundsWithOptions(titleLine, .useGlyphPathBounds)
let titleX = (targetW - titleBounds.width) / 2.0 - titleBounds.origin.x
let titleY: CGFloat = isVertical ? (subtitle.isEmpty ? 200 : 250) : (subtitle.isEmpty ? 140 : 180)

ctx.saveGState()
ctx.textPosition = CGPoint(x: titleX, y: titleY)
CTLineDraw(titleLine, ctx)
ctx.restoreGState()

// 5. Subtitle under Title
if !subtitle.isEmpty {
    let subFontSize: CGFloat = isVertical ? 40 : 34
    let subFont = NSFont.systemFont(ofSize: subFontSize, weight: .semibold)
    let subAttrs: [NSAttributedString.Key: Any] = [
        .font: subFont,
        .foregroundColor: NSColor(red: 1.0, green: 0.92, blue: 0.35, alpha: 1.0), // Warm gold highlight
        .shadow: titleShadow
    ]
    let subStr = NSAttributedString(string: subtitle, attributes: subAttrs)
    let subLine = CTLineCreateWithAttributedString(subStr)
    let subBounds = CTLineGetBoundsWithOptions(subLine, .useGlyphPathBounds)
    let subX = (targetW - subBounds.width) / 2.0 - subBounds.origin.x
    let subY: CGFloat = isVertical ? 175 : 110

    ctx.saveGState()
    ctx.textPosition = CGPoint(x: subX, y: subY)
    CTLineDraw(subLine, ctx)
    ctx.restoreGState()
}

// Encode and save PNG
guard let outCGImage = ctx.makeImage() else {
    print("Failed to create final CGImage")
    exit(1)
}

let outRep = NSBitmapImageRep(cgImage: outCGImage)
guard let pngData = outRep.representation(using: .png, properties: [:]) else {
    print("Failed to encode PNG output")
    exit(1)
}

let outURL = URL(fileURLWithPath: outputPath)
try pngData.write(to: outURL)
print("Intro card rendered: \(outputPath)")
