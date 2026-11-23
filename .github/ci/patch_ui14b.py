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
    s = re.sub(r'String\(localized:\s*([^"()][^)]*?)\)',
               r'NSLocalizedString(\1, comment: "")', s)

    # ---- String.LocalizationValue 类型参数 → String
    s = s.replace("_ key: String.LocalizationValue", "_ key: String")

    # ---- LocalizedStringResource 类型 → String
    s = s.replace("labelKey: LocalizedStringResource", "labelKey: String")
    s = s.replace("LocalizedStringResource) -> String", ") -> String")

    # ---- Regex 字面量 + wholeMatch(of:)
    s = s.replace(
        "static let keyRegex = /^[A-Za-z][A-Za-z0-9_]*$/",
        'static let keyRegex = try! NSRegularExpression(pattern: "^[A-Za-z][A-Za-z0-9_]*$")')
    s = s.replace(
        "key.wholeMatch(of: keyRegex) != nil",
        "keyRegex.firstMatch(in: key, range: NSRange(key.startIndex..., in: key)) != nil")

    # ---- DynamicTypeSize 属性 → UIContentSizeCategory（缩放降级）
    s = re.sub(
        r"var dynamicTypeSize: DynamicTypeSize \{[^}]*\}",
        "var dynamicTypeSize: UIContentSizeCategory { .unspecified }", s, count=1)

    # ---- .indigo → 等效 RGB
    s = s.replace("tint: .indigo", "tint: Color(red: 0.35, green: 0.35, blue: 0.85)")

    # ---- 声明改写：dismiss 环境
    s = s.replace("@Environment(\\.dismiss) private var dismiss",
                  "@Environment(DismissEnvKey()) private var dismiss")
    s = s.replace("@Environment(\\.dismiss) var dismiss",
                  "@Environment(DismissEnvKey()) var dismiss")

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

/// iOS 15 的 @Environment(\.dismiss)。声明处写法一致（dismiss() 调用零改动），
/// iOS 14 下由 _DismissBridge 桥到 presentationMode。
struct DismissActionCompat {
    let dismiss: () -> Void
}

struct DismissEnvKey: EnvironmentKey {
    static let defaultValue = DismissActionCompat { }
}

extension EnvironmentValues {
    var dismiss: DismissActionCompat {
        get { self[DismissEnvKey.self] }
        set { self[DismissEnvKey.self] = newValue }
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
'''
    anchor.write_text(text + SHIM, encoding="utf-8")
    print("shim batch2 appended")
