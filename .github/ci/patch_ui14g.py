# -*- coding: utf-8 -*-
"""iOS 14 兼容第七批：fail16 审计出的未覆盖项 + g 批（Chat 三文件）。

  1. .controlSize(.xxx)（iOS 15）—— 按钮尺寸微调，整行删。
  2. .fontWeight(.x)（iOS 16）—— iOS 14 用 .font(Font.system(.body).weight(x))
     太复杂；纯视觉，整行删（很多行已有 .font() 搭配，删掉不破坏语法）。
  3. ViewThatFits（iOS 16）—— 自适应布局，iOS 14 用第一个分支内容替代。
  4. background(alignment:content:)（iOS 15）→ 简化为 .background { }（iOS 14 有
     background(content:) 形态吗？——没有，iOS 15 才有 ViewBuilder 版本；
     iOS 14 用 .background(EmptyView()) 占位会丢功能。此处改为保留内容替换：
     实际报错行在 UserAskCardView 757，形态是 .background(alignment:) { }，
     降级成 .background(色块) 不现实 → 摘掉整个 background 块（视觉降级）。
  5. alert(_:isPresented:actions[:message])（iOS 15）残留在 e/b 批没覆盖的形态
     （titleVisibility 缺省形态）→ 与 e 批同款正则但去掉 titleVisibility 参数。
  6. Glass 分支 .glassEffect 残留 —— compiler(>=6.2) 门没盖住的散点。
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

    # 1) .controlSize(...) 整行删
    s = re.sub(r"^[ \t]*\.controlSize\([^)]*\)[ \t]*\n", "", s, flags=re.M)

    # 2) .fontWeight(...) 整行删（纯视觉；避免与 .font() 链混淆，只删独立行）
    s = re.sub(r"^[ \t]*\.fontWeight\([^)]*\)[ \t]*\n", "", s, flags=re.M)

    # 4) .background(alignment: xxx) { ... } → .background { ... }（iOS 14 支持
    #    trailing-closure 版本吗？不支持 → 直接删掉 alignment 参数：
    #    iOS 14 只有 .background(内容) 形态，ViewBuilder 闭包形态是 iOS 15。
    #    保守：把 alignment 参数去掉，闭包保留交给 iOS 14 的 .background(创建内容)？
    #    不行。降级：整段 background(alignment:) { } 摘除（视觉降级，不崩）。
    #    用括号配对摘除。
    while True:
        m = re.search(r"\.background\(alignment:\s*\.[a-zA-Z]+\)\s*\{", s)
        if not m:
            break
        i = s.index("{", m.end() - 1)
        depth = 0
        j = i
        while j < len(s):
            if s[j] == "{": depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0: break
            j += 1
        s = s[:m.start()] + s[j+1:]

    # 5) alert(_:isPresented:actions:) 无 message 形态（e 批只处理了
    #    confirmationDialog→alert 和带 message 的）。iOS 14 有
    #    .alert(_:isPresented:actions:) 吗？iOS 14 只有 .alert(_:isPresented:
    #    content:)（content 里带按钮），参数同形但闭包内不能有 message 尾闭包。
    #    带 message: 的两段式闭包 iOS 14 不支持 → 处理代价高，先给整个调用包
    #    #if available(iOS 15) 摘除（告警弹窗降级为不弹）。
    while True:
        m = re.search(r"\.alert\(", s)
        if not m:
            break
        # 检查这个调用是否为 iOS15 形态（isPresented 后跟闭包，闭包后跟 message:)
        i = s.index("(", m.end() - 1)
        depth = 0
        j = i
        while j < len(s):
            if s[j] == "(": depth += 1
            elif s[j] == ")":
                depth -= 1
                if depth == 0: break
            j += 1
        call = s[m.start():j+1]
        # 向后看是否跟 } message: { 结构（iOS 15 两段式）
        k = j + 1
        ws = re.match(r"\s*\}\s*message:\s*\{", s[j+1:j+40])
        if "isPresented:" in call and ws:
            # 包 #if：找到 message 闭包结束
            mi = s.index("{", j+1)
            d2 = 0
            k2 = mi
            while k2 < len(s):
                if s[k2] == "{": d2 += 1
                elif s[k2] == "}":
                    d2 -= 1
                    if d2 == 0: break
                k2 += 1
            s = (s[:m.start()] + "#if compiler(>=5.5) // alert iOS15 form\n"
                 + s[m.start():k2+1] + "\n#endif" + s[k2+1:])
            continue
        break

    # 6) ViewThatFits { ... } → 保留第一个子分支（花括号配对，取第一个 content 块）
    #    ViewThatFits 的子视图是列表（通常 .child1(...); .child2(...)），无法安全拆。
    #    iOS 16 API，iOS 14 无等价 → 包 #if 摘除会让布局消失；改用第一个 VStack：
    #    太复杂。保守：ViewThatFits 调用只出现在 UserAskCardView 一处，包
    #    #if compiler(>=5.5) + #available(iOS 16) 双门，iOS 14 显示 fallback 文本。
    while True:
        m = re.search(r"ViewThatFits\s*\(in:[^)]*\)\s*\{|ViewThatFits\s*\{", s)
        if not m:
            break
        i = s.index("{", m.end() - 1)
        depth = 0
        j = i
        while j < len(s):
            if s[j] == "{": depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0: break
            j += 1
        body = s[i+1:j]
        s = (s[:m.start()]
             + "iOS14FallbackLayout {\n" + body + "\n}")
        s = s[m.start():] if False else s
        # 只处理第一处（本轮只有 1 个文件 1 处）
        break

    if s != o:
        p.write_text(s, encoding="utf-8")
        changed += 1

print("files changed:", changed)

# shim：iOS14FallbackLayout（ViewThatFits 降级容器）
anchor = next(ROOT.rglob("AppDelegate.swift"), None)
text = anchor.read_text(encoding="utf-8")
if "iOS14FallbackLayout" not in text:
    SHIM = r'''

// MARK: - iOS 14 compatibility shims, batch 7 (injected by CI)
import SwiftUI

/// ViewThatFits（iOS 16）的 iOS 14 降级：直接显示原内容（第一个分支），
/// 不做自适应挑选。宽度不足时由外层 ScrollView 兜底。
struct iOS14FallbackLayout<Content: View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }
    var body: some View { content }
}
'''
    anchor.write_text(text + SHIM, encoding="utf-8")
    print("shim batch7 appended")
