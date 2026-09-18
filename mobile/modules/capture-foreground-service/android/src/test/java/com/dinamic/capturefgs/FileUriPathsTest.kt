package com.dinamic.capturefgs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class FileUriPathsTest {
  @Test
  fun preservesPlusInFileUri() {
    val path = FileUriPaths.toAbsolutePath("file:///data/local/tmp/item+A.jpg")
    assertEquals("/data/local/tmp/item+A.jpg", path)
  }

  @Test
  fun decodesPercent2BToPlus() {
    val path = FileUriPaths.toAbsolutePath("file:///data/local/tmp/item%2BA.jpg")
    assertEquals("/data/local/tmp/item+A.jpg", path)
  }

  @Test
  fun decodesPercent20ToSpace() {
    val path = FileUriPaths.toAbsolutePath("file:///data/local/tmp/item%20A.jpg")
    assertEquals("/data/local/tmp/item A.jpg", path)
  }

  @Test
  fun preservesLiteralSpaceInFileUri() {
    val path = FileUriPaths.toAbsolutePath("file:///data/local/tmp/item A.jpg")
    assertEquals("/data/local/tmp/item A.jpg", path)
  }

  @Test
  fun preservesUnicode() {
    val path = FileUriPaths.toAbsolutePath("file:///data/local/tmp/foto_ñ_ü.jpg")
    assertEquals("/data/local/tmp/foto_ñ_ü.jpg", path)
  }

  @Test
  fun acceptsAbsolutePathWithoutScheme() {
    val abs = "/data/local/tmp/plain.jpg"
    assertEquals(abs, FileUriPaths.toAbsolutePath(abs))
  }

  @Test
  fun rejectsUnsupportedScheme() {
    assertThrows(IllegalArgumentException::class.java) {
      FileUriPaths.toAbsolutePath("content://media/external/images/1")
    }
  }

  @Test
  fun percentDecodePath_preservesLiteralPlus() {
    assertEquals(
      "/data/local/tmp/item+A.jpg",
      FileUriPaths.percentDecodePath("/data/local/tmp/item+A.jpg"),
    )
  }

  @Test
  fun percentDecodePath_decodesPercent2BOnly() {
    assertEquals(
      "/data/local/tmp/item+A.jpg",
      FileUriPaths.percentDecodePath("/data/local/tmp/item%2BA.jpg"),
    )
  }

  @Test
  fun percentDecodePath_decodesUtf8NTilde() {
    assertEquals("foto_ñ.jpg", FileUriPaths.percentDecodePath("foto_%C3%B1.jpg"))
  }

  @Test
  fun percentDecodePath_decodesUtf8UUmlaut() {
    assertEquals("foto_ü.jpg", FileUriPaths.percentDecodePath("foto_%C3%BC.jpg"))
  }

  @Test
  fun percentDecodePath_decodesUtf8CJK() {
    assertEquals("日.jpg", FileUriPaths.percentDecodePath("%E6%97%A5.jpg"))
  }

  @Test
  fun percentDecodePath_leavesInvalidPercentZZUnchanged() {
    assertEquals("item%ZZx.jpg", FileUriPaths.percentDecodePath("item%ZZx.jpg"))
  }

  @Test
  fun percentDecodePath_leavesTrailingPercentUnchanged() {
    assertEquals("item%.jpg", FileUriPaths.percentDecodePath("item%.jpg"))
  }

  @Test
  fun percentDecodePath_spaceViaPercent20() {
    assertEquals("item A.jpg", FileUriPaths.percentDecodePath("item%20A.jpg"))
  }
}
