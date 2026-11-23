# -*- coding: utf-8 -*-
"""iOS 14 兼容第六批：TimelineView / AnyShapeStyle / monospacedDigit / 残余。

第十轮（45177416658）暴露的新一批 API，前五批没覆盖：
  1. TimelineView(.periodic(from:by:))（iOS 15）—— 倒计时用，iOS 14 退化为
     静态文本（不逐秒刷新，时间显示的秒数不再跳动，功能可用）。
  2. AnyShapeStyle（iOS 15）—— 条件背景，直接换成条件 Color。
  3. .monospacedDigit()（iOS 15）—— 字体数字等宽增强，整行修饰删掉。
  4. background(_:in:) 残余（第二 批正则只处理了 Capsule/Circle 简单形态）——
     泛化：in: 后面跟任意 Shape() 形式。
  5. .tint（iOS 15 修饰器形态）与 Glass 分支的遗留。
"""

import pathlib
import re

ROOT = pathlib.Path("src/ios")
SKIP_PARTS = {"MinisTests", "MinisUITests", "Tests", "Pods", "build_dd",
              "build", "DerivedData", "AgentWidget", "FileProvider"}

changed = 0
for p in ROOT.rglob("*.swift"):
    if any(part in SKIP_PARTS for part in p.parts):
        continue
    s = p.read_text(encoding="utf-8")
    o = s

    # 1) TimelineView(.periodic(from: .now, by: N)) { ctx in ... } —— 找到闭合并降级。
    #    直接把 TimelineView 包裹剥掉，保留 ctx 换成固定 Date() 的内部块？
    #    块内引用 ctx.date 的地方需要替换。用保守做法：整个 TimelineView 段落
    #    用花括号配对摘除后，以内容体 + 固定时间重建。
    def _downgrade_timeline(src):
        out = src
        while True:
            m = re.search(r"TimelineView\(\.periodic\(from:\s*\.now,\s*by:\s*[\d.]+\)\)\s*\{\s*(\w+)\s+in", out)
            if not m:
                break
            # 找匹配的闭合括号
            i = out.index("{", m.end() - 1)
            depth = 0
            j = i
            while j < len(out):
                if out[j] == "{": depth += 1
                elif out[j] == "}":
                    depth -= 1
                    if depth == 0: break
                j += 1
            body = out[m.end():j]          # ctx in { body }
            ctx = m.group(1)
            # 块内 ctx.date → 固定 Date()（倒计时静止）
            body2 = re.sub(r"\b" + ctx + r"\.date\b", "Date()", body)
            replacement = ("Group { let " + ctx + " = FixedTimelineContext(); _ = " + ctx +
                           "\n" + body2 + "\n}")
            out = out[:m.start()] + replacement + out[j+1:]
        return out

    class FixedTimelineContext:
        pass

    # 生成 shim 时需要 FixedTimelineContext 类型（见下方注入）
    s = _downgrade_timeline(s)
    # TimelineView(.periodic) 以外的其它 TimelineView 用法：包 #if 摘除会丢功能，
    # 先统计（本轮日志只报 periodic 形态）。

    # 2) AnyShapeStyle(A) : AnyShapeStyle(B) 条件形态 → (cond ? A : B) 已是
    #    三元的一部分，直接把 AnyShapeStyle( 换成 Color( 不安全（可能是渐变）。
    #    本轮只有 Color(UIColor.x) 形态 → 直接去壳。
    s = s.replace("AnyShapeStyle(Color(UIColor.tertiarySystemFill))",
                  "Color(UIColor.tertiarySystemFill)")
    s = re.sub(r"AnyShapeStyle\(Color\(([^)]+)\)\)", r"Color(\1)", s)
    s = s.replace("AnyShapeStyle(Color.clear)", "Color.clear")

    # 3) .monospacedDigit() 整行删（纯视觉）
    s = re.sub(r"^[ \t]*\.monospacedDigit\(\)[ \t]*\n", "", s, flags=re.M)
    s = re.sub(r"\.monospacedDigit\(\)", "", s)     # 链中形态

    # 4) background(X, in: Shape()) 泛化版（第一批只处理 Capsule/Circle）
    s = re.sub(r"\.background\(([^()]*(?:\([^()]*\)[^()]*)*), in: ([A-Z][A-Za-z]*\([^()]*\))\)",
               r".background(\2.fill(\1))", s)

    # 5) .tint( 修饰器（iOS 15）→ 不动（tint(Color) 参数形态在 iOS 14 也有,
    #    只有 .tint 无参形态是 15）。删无参形态：
    s = re.sub(r"^[ \t]*\.tint\(\)[ \t]*\n", "", s, flags=re.M)

    if s != o:
        p.write_text(s, encoding="utf-8")
        changed += 1

print("files changed:", changed)

# shim
anchor = next(ROOT.rglob("AppDelegate.swift"), None)
text = anchor.read_text(encoding="utf-8")
if "FixedTimelineContext" not in text:
    SHIM = r'''

// MARK: - iOS 14 compatibility shims, batch 6 (injected by CI)
import SwiftUI

/// TimelineView 降级用的固定上下文：ctx.date 恒为当前时间（构建时取一次），
/// 倒计时不再逐秒刷新。
struct FixedTimelineContext {
    let date: Date = Date()
}
'''
    anchor.write_text(text + SHIM, encoding="utf-8")
    print("shim batch6 appended")
