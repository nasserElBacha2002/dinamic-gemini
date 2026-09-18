package com.dinamic.capturefgs

import java.io.ByteArrayOutputStream
import java.nio.charset.StandardCharsets

/**
 * Normalize absolute filesystem paths and file:// URIs for native I/O.
 *
 * Pure JVM implementation — does **not** use android.net.Uri or
 * java.net.URLDecoder. Form-urlencoded rules would turn '+' into space and
 * corrupt valid filenames like "item+A.jpg". Percent-decoding is applied
 * only for %HH sequences; literal '+' is preserved.
 */
object FileUriPaths {
  @JvmStatic
  fun toAbsolutePath(pathOrUri: String): String {
    val trimmed = pathOrUri.trim()
    if (trimmed.isEmpty()) {
      throw IllegalArgumentException("empty path")
    }
    if (!trimmed.contains("://") && !trimmed.startsWith("file:")) {
      return trimmed
    }
    val schemeEnd = trimmed.indexOf(':')
    if (schemeEnd <= 0) {
      throw IllegalArgumentException("malformed uri")
    }
    val scheme = trimmed.substring(0, schemeEnd)
    if (!scheme.equals("file", ignoreCase = true)) {
      throw IllegalArgumentException("unsupported uri scheme: $scheme")
    }
    var rest = trimmed.substring(schemeEnd + 1)
    // file:/path  or  file:///path  or  file://host/path
    if (rest.startsWith("//")) {
      rest = rest.substring(2)
      if (!rest.startsWith("/")) {
        val slash = rest.indexOf('/')
        if (slash < 0) {
          throw IllegalArgumentException("file uri missing path")
        }
        rest = rest.substring(slash)
      }
    }
    if (rest.isEmpty()) {
      throw IllegalArgumentException("file uri empty path")
    }
    return percentDecodePath(rest)
  }

  /**
   * Decode %HH sequences as raw bytes, then interpret the byte stream as UTF-8.
   *
   * - Literal '+' is preserved (not treated as space).
   * - Valid %HH pairs append a single byte 0–255.
   * - Literal characters are appended as their UTF-8 encoding
   *   (ASCII as a single byte).
   * - Invalid % sequences (non-hex digits, or a trailing '%' / truncated
   *   %H with no second hex digit) are left unchanged: the '%' and any
   *   following characters are appended as literal UTF-8 bytes.
   */
  @JvmStatic
  fun percentDecodePath(path: String): String {
    if (!path.contains('%')) {
      return path
    }
    val bytes = ByteArrayOutputStream(path.length)
    var i = 0
    while (i < path.length) {
      val c = path[i]
      if (c == '%' && i + 2 < path.length) {
        val v1 = hexValue(path[i + 1])
        val v2 = hexValue(path[i + 2])
        if (v1 >= 0 && v2 >= 0) {
          bytes.write(v1 * 16 + v2)
          i += 3
          continue
        }
      }
      // Literal char (including invalid '%' sequences): UTF-8 bytes of that char.
      val utf8 = c.toString().toByteArray(StandardCharsets.UTF_8)
      bytes.write(utf8)
      i += 1
    }
    return String(bytes.toByteArray(), StandardCharsets.UTF_8)
  }

  private fun hexValue(c: Char): Int {
    return when (c) {
      in '0'..'9' -> c - '0'
      in 'a'..'f' -> c - 'a' + 10
      in 'A'..'F' -> c - 'A' + 10
      else -> -1
    }
  }
}
