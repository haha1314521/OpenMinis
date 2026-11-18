import glob, pathlib, re, sys

roots = glob.glob(str(pathlib.Path.home() / "Library/Developer/Xcode/DerivedData/*/SourcePackages/checkouts"))
patched = []

FALLBACK = '''  public func bytes(for request: HTTPRequest) async throws -> (HTTPByteStream, HTTPResponse) {
    let (data, response) = try await data(for: request)
    let text = String(decoding: data, as: UTF8.self)
    let stream = AsyncThrowingStream<String, Error> { continuation in
      for line in text.split(separator: "\\n", omittingEmptySubsequences: false) {
        continuation.yield(String(line))
      }
      continuation.finish()
    }
    return (.lines(stream), response)
  }
'''

for root in roots:
    for p in pathlib.Path(root).rglob("URLSessionHTTPClientAdapter.swift"):
        s = p.read_text(encoding="utf-8")
        if "urlSession.bytes(for:" not in s:
            continue
        start = s.index("  public func bytes(for request: HTTPRequest) async throws -> (HTTPByteStream, HTTPResponse) {")
        # 找函数结束：从 start 起数花括号
        i = s.index("{", start)
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{": depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        s = s[:start] + FALLBACK + s[j+1:]
        p.write_text(s, encoding="utf-8")
        patched.append(str(p))
print("patched:", patched)
if not patched:
    print("WARN: no SwiftAnthropic adapter found")
