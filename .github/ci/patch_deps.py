import pathlib, sys

ROOT = pathlib.Path("src/ios/build_dd/SourcePackages/checkouts/SwiftAnthropic")
if not ROOT.exists():
    print("SwiftAnthropic checkout not found at", ROOT)
    sys.exit(1)

pkg = ROOT / "Package.swift"
s = pkg.read_text(encoding="utf-8")
s2 = s.replace(".iOS(.v15)", ".iOS(.v14)")
pkg.write_text(s2, encoding="utf-8")
print("package platforms patched:", s != s2)

adapter = ROOT / "Sources/Anthropic/Private/Networking/URLSessionHTTPClientAdapter.swift"
NEW = r'''import Foundation

#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

#if !os(Linux)
/// Adapter that implements HTTPClient protocol using URLSession
public class URLSessionHTTPClientAdapter: HTTPClient {

  /// Initializes a new URLSessionHTTPClientAdapter with the provided URLSession
  /// - Parameter urlSession: The URLSession instance to use. Defaults to `URLSession.shared`.
  public init(urlSession: URLSession = .shared) {
    self.urlSession = urlSession
  }

  /// Fetches data for a given HTTP request
  public func data(for request: HTTPRequest) async throws -> (Data, HTTPResponse) {
    let urlRequest = try createURLRequest(from: request)
    let (data, urlResponse) = try await performData(urlRequest)
    guard let httpURLResponse = urlResponse as? HTTPURLResponse else {
      throw URLError(.badServerResponse)
    }
    let response = HTTPResponse(
      statusCode: httpURLResponse.statusCode,
      headers: convertHeaders(httpURLResponse.allHeaderFields))
    return (data, response)
  }

  /// Fetches a byte stream for a given HTTP request.
  /// iOS 15 之前没有 URLSession.bytes(for:)，退化为整包取回再按行切分。
  public func bytes(for request: HTTPRequest) async throws -> (HTTPByteStream, HTTPResponse) {
    let urlRequest = try createURLRequest(from: request)
    if #available(iOS 15.0, macOS 12.0, *) {
      let (asyncBytes, urlResponse) = try await urlSession.bytes(for: urlRequest)
      guard let httpURLResponse = urlResponse as? HTTPURLResponse else {
        throw URLError(.badServerResponse)
      }
      let response = HTTPResponse(
        statusCode: httpURLResponse.statusCode,
        headers: convertHeaders(httpURLResponse.allHeaderFields))
      let stream = AsyncThrowingStream<String, Error> { continuation in
        Task {
          do {
            for try await line in asyncBytes.lines {
              continuation.yield(line)
            }
            continuation.finish()
          } catch {
            continuation.finish(throwing: error)
          }
        }
      }
      return (.lines(stream), response)
    }
    let (data, urlResponse) = try await performData(urlRequest)
    guard let httpURLResponse = urlResponse as? HTTPURLResponse else {
      throw URLError(.badServerResponse)
    }
    let response = HTTPResponse(
      statusCode: httpURLResponse.statusCode,
      headers: convertHeaders(httpURLResponse.allHeaderFields))
    let text = String(decoding: data, as: UTF8.self)
    let stream = AsyncThrowingStream<String, Error> { continuation in
      for line in text.split(separator: "\n", omittingEmptySubsequences: false) {
        continuation.yield(String(line))
      }
      continuation.finish()
    }
    return (.lines(stream), response)
  }

  private let urlSession: URLSession

  private func performData(_ urlRequest: URLRequest) async throws -> (Data, URLResponse) {
    if #available(iOS 15.0, macOS 12.0, *) {
      return try await urlSession.data(for: urlRequest)
    }
    return try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<(Data, URLResponse), Error>) in
      urlSession.dataTask(with: urlRequest) { data, response, error in
        if let error = error {
          continuation.resume(throwing: error)
          return
        }
        guard let data = data, let response = response else {
          continuation.resume(throwing: URLError(.badServerResponse))
          return
        }
        continuation.resume(returning: (data, response))
      }.resume()
    }
  }

  /// Converts our HTTPRequest to URLRequest
  private func createURLRequest(from request: HTTPRequest) throws -> URLRequest {
    var urlRequest = URLRequest(url: request.url)
    urlRequest.httpMethod = request.method.rawValue

    for (key, value) in request.headers {
      urlRequest.setValue(value, forHTTPHeaderField: key)
    }

    urlRequest.httpBody = request.body

    return urlRequest
  }

  /// Converts HTTPURLResponse headers to a dictionary [String: String]
  private func convertHeaders(_ headers: [AnyHashable: Any]) -> [String: String] {
    var result = [String: String]()
    for (key, value) in headers {
      if let keyString = key as? String, let valueString = value as? String {
        result[keyString] = valueString
      }
    }
    return result
  }
}
#endif'''
adapter.write_text(NEW, encoding="utf-8")
print("adapter patched:", adapter)
