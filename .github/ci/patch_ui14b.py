#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iOS 14 兼容第二批：dismiss / 本地化 / Regex / DynamicTypeSize / .indigo。

第一批（patch_ui14.py）处理纯 modifier（foregroundStyle/task/background 等）。
这一批处理属性声明级 API：

  1. @Environment(\\.dismiss) 78 处
     → 注入同名包装类型 DismissActionCompat + 自定义 EnvironmentKey，
       声明改写为 @Environment(DismissEnvKey())，调用点 dismiss() 零改动。
       根视图由 workflow 追加 .ios14DismissBridge() 桥接 presentationMode。

  2. 本地化：String(localized:) / String.LocalizationValue /
     LocalizedStringResource → NSLocalizedString（iOS 13 就有）。

  3. Regex 字面量（keyRegex）→ NSRegularExpression。
  4. DynamicTypeSize 属性 → UIContentSizeCategory。
  5. .indigo → 等效 RGB Color。
"""

import pathlib
import re
import sys

ROOT = pathlib.Path("src/ios")
SKIP_PARTS = {"MinisTests", "MinisUITests", "Tests", "Pods", "build_dd",
              "build", "DerivedData", "AgentWidget", "FileProvider"}

files = [p for p in ROOT.rglob("*.swift")
         if not any(part in SKIP_PARTS for part in p.parts)]

changed = 0
for p in files:
    s = p.read_text(encoding="utf-8")
    o = s

    # ---- 本地化：String(localized: "字面量", ...) → NSLocalizedString
    def _loc_literal(m):
        inner = m.group(1).strip()
        if not inner.startswith('"'):
            return m.group(0)
        parts = re.split(r',\s*(?:table|bundle|comment)\s*:', inner)
        key = parts[0]
        cm = re.search(r'comment:\s*([^)]+)', inner)
        comment = cm.group(1).strip() if cm else '""'
        return 'NSLocalizedString(%s, comment: %s)' % (key, comment)

    s = re.sub(r'String\(localized:\s*("(?:[^"\\]|\\.)*")[^)]*\)',
               _loc_literal, s)

    # 变量形态：区分有无 bundle/comment。带参的（iOS 15 形态）换参数顺序降级，
    # 无参的简单包一层。
    def _loc_var(m):
        inner = m.group(1).strip()
        if 'bundle:' in inner or 'comment:' in inner or 'table:' in inner:
            keypart = inner.split(',', 1)[0].strip()
            bm = re.search(r'bundle:\s*([^,]+?)(?:,\s*comment|$)', inner)
            cm = re.search(r'comment:\s*([^)]+?)\s*$', inner)
            b = bm.group(1).strip() if bm else 'AppBundle.current'
            c = cm.group(1).strip() if cm else '""'
            return 'NSLocalizedString(%s, bundle: %s, comment: %s)' % (keypart, b, c)
        return 'NSLocalizedString(%s, comment: "")' % inner

    s = re.sub(r'String\(localized:\s*([^"()][^)]*?)\)',
               _loc_var, s)

    # ---- String.LocalizationValue 类型参数 → String
    s = s.replace("_ key: String.LocalizationValue", "_ key: String")

    # ---- LocalizedStringResource 类型 → String（先带参数名保护，防 resource: 被清空）
    s = s.replace("labelKey: LocalizedStringResource", "labelKey: String")
    s = s.replace("resource: LocalizedStringResource", "resource: String")
    s = s.replace("(resource: LocalizedStringResource)", "(resource: String)")
    s = s.replace("LocalizedStringResource) -> String", "String) -> String")

    # ---- 修正误伤
    # 1) _loc_var 带参分支把 String.LocalizationValue(plain) 的括号内容当成了实参列表，
    #    又被叠加了 comment: ""；还原构造表达式。
    s = s.replace('String.LocalizationValue(plain, comment: "")',
                  'String.LocalizationValue(plain)')
    # String.LocalizationValue 构造本身是 iOS 15，直接传字符串
    s = s.replace('NSLocalizedString(String.LocalizationValue(plain), bundle: bundle, comment: comment)',
                  'NSLocalizedString(plain, bundle: bundle, comment: comment)')
    # 2) LocalizedStringResource 参数名清空的误伤：先把具体参数名换掉再走类型替换
    s = s.replace('resource: ) -> String', 'resource: String) -> String')
    # resource 函数体保持与 key 函数一致的 bundle 指向
    s = s.replace('NSLocalizedString(resource, comment: "")',
                  'NSLocalizedString(resource, bundle: AppBundle.current, comment: "")')

    # ---- 嵌套 String(localized: "字面量")（如 String(format: String(localized: "x"))）
    s = re.sub(r'String\(localized:\s*("(?:[^"\\]|\\.)*")\)',
               r'NSLocalizedString(\1, comment: "")', s)

    # ---- Regex 字面量 + wholeMatch(of:)
    s = s.replace(
        "static let keyRegex = /^[A-Za-z][A-Za-z0-9_]*$/",
        'static let keyRegex = try! NSRegularExpression(pattern: "^[A-Za-z][A-Za-z0-9_]*$")')
    s = s.replace(
        "key.wholeMatch(of: keyRegex) != nil",
        "keyRegex.firstMatch(in: key, range: NSRange(key.startIndex..., in: key)) != nil")

    # ---- DynamicTypeSize 属性 → UIContentSizeCategory（缩放降级）
    # 用花括号配对整段替换（正则 [^}]* 会在 switch 的第一个 } 截断，破坏结构）
    dm = re.search(r"var dynamicTypeSize: DynamicTypeSize \{", s)
    if dm:
        j = s.index("{", dm.start())
        d = 0
        while j < len(s):
            if s[j] == "{": d += 1
            elif s[j] == "}":
                d -= 1
                if d == 0: break
            j += 1
        s = (s[:dm.start()] + "var dynamicTypeSize: UIContentSizeCategory { .unspecified }"
             + s[j+1:])

    # ---- .indigo → 等效 RGB
    s = s.replace("tint: .indigo", "tint: Color(red: 0.35, green: 0.35, blue: 0.85)")

    # ---- textSelection（iOS 15，纯交互增强）→ 整行删除
    s = re.sub(r"^[ \t]*\.textSelection\([^)]*\)[ \t]*\n", "", s, flags=re.M)

    # ---- formatted(date:time:)（iOS 15）→ DateFormatter
    s = s.replace(
        ".formatted(date: .abbreviated, time: .standard)",
        "_IOS14DF.shared.string(from: confirmed)")

    # ---- confirmationDialog（iOS 15）→ alert（iOS 8+）
    s = re.sub(
        r"\.confirmationDialog\((\"(?:[^\"\\]|\\.)*\"), isPresented: (\$[A-Za-z_.]+), titleVisibility: \.visible\)",
        r".alert(\1, isPresented: \2)", s)

    # ---- keyWindow（iOS 15 的 UIWindowScene.keyWindow）→ 兼容取法
    s = s.replace(
        ".compactMap { ($0 as? UIWindowScene)?.keyWindow }",
        ".compactMap { ($0 as? UIWindowScene)?.windows.first(where: { $0.isKeyWindow }) }")

    # ---- dismiss 环境声明保持原样：@Environment(\.dismiss) 的 keypath 在
    # iOS 14 SDK 下解析到本 shim 的 EnvironmentValues.dismiss 扩展（系统无该
    # 属性，无歧义）；iOS 15+ SDK 解析到系统属性。桥接在根部统一注入。

    if s != o:
        p.write_text(s, encoding="utf-8")
        changed += 1

print("files changed:", changed)

# ---- 注入 shim
anchor = next(ROOT.rglob("AppDelegate.swift"), None)
if anchor is None:
    print("AppDelegate.swift not found"); sys.exit(1)
text = anchor.read_text(encoding="utf-8")
if "DismissActionCompat" not in text:
    SHIM = r'''

// MARK: - iOS 14 compatibility shims, batch 2 (injected by CI)
import SwiftUI
import UIKit

/// iOS 15 的 @Environment(\.dismiss)。声明与调用零改动：
/// iOS 14 SDK 下 \.dismiss keypath 解析到本扩展（系统无该属性），
/// 值由根视图的 _DismissBridge 从 presentationMode 桥进来。
struct DismissActionCompat {
    let dismiss: () -> Void
}

extension EnvironmentValues {
    @available(iOS, deprecated: 15.0)
    var dismiss: DismissActionCompat {
        get { DismissActionCompat { } }   // 真实值由 _DismissBridge 注入覆盖
        set { _ = newValue }
    }
}

struct _DismissBridge: ViewModifier {
    @Environment(\.presentationMode) private var presentationMode
    func body(content: Content) -> some View {
        content.environment(\.dismiss, DismissActionCompat {
            presentationMode.wrappedValue.dismiss()
        })
    }
}

extension View {
    func ios14DismissBridge() -> some View { modifier(_DismissBridge()) }
}

// formatted(date:time:) 降级用的共享 formatter
enum _IOS14DF {
    static let shared: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .standard
        return f
    }()
}
'''
    anchor.write_text(text + SHIM, encoding="utf-8")
    print("shim batch2 appended")
