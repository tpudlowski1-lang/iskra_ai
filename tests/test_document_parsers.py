import io
import unittest
import zipfile

from pypdf import PdfWriter

from iskra.documents.parsers import (
    MAX_UPLOAD_BYTES,
    parse_document,
)


def make_docx(xml):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
    return stream.getvalue()


class DocumentParserTests(unittest.TestCase):
    def test_txt_utf8_is_normalized_and_chunked(self):
        data = ("Zażółć gęślą jaźń. " * 150).encode("utf-8")
        parsed = parse_document("../oferta.txt", data)
        self.assertEqual(parsed.filename, "oferta.txt")
        self.assertEqual(parsed.extension, ".txt")
        self.assertGreater(len(parsed.chunks), 1)
        self.assertIn("Zażółć", parsed.chunks[0])

    def test_txt_cp1250_fallback(self):
        parsed = parse_document("notatka.txt", "Zażółć".encode("cp1250"))
        self.assertIn("Zażółć", parsed.chunks[0])

    def test_empty_binary_and_unsupported_files_are_rejected(self):
        for filename, data in [
            ("empty.txt", b""),
            ("binary.txt", b"\x00\x01\x02"),
            ("program.exe", b"not allowed"),
        ]:
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    parse_document(filename, data)

    def test_upload_and_extracted_text_limits_are_enforced(self):
        with self.assertRaises(ValueError):
            parse_document("large.txt", b"a" * (MAX_UPLOAD_BYTES + 1))
        with self.assertRaises(ValueError):
            parse_document("large.txt", ("x" * 1_500_001).encode("utf-8"))

    def test_docx_extracts_only_document_xml_text(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Poufna oferta firmy.</w:t></w:r></w:p>
            <w:p><w:r><w:t>Drugi akapit.</w:t></w:r></w:p>
          </w:body>
        </w:document>'''
        parsed = parse_document("oferta.docx", make_docx(xml))
        self.assertEqual(parsed.extension, ".docx")
        joined = "\n".join(parsed.chunks)
        self.assertIn("Poufna oferta firmy.", joined)
        self.assertIn("Drugi akapit.", joined)

    def test_docx_dtd_and_entity_payload_is_rejected(self):
        xml = b'''<!DOCTYPE w:document [<!ENTITY x "expanded">]>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body>
        </w:document>'''
        with self.assertRaises(ValueError):
            parse_document("attack.docx", make_docx(xml))

    def test_docx_compression_ratio_is_bounded(self):
        xml = (
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:body><w:p><w:r><w:t>' + (b"A" * 1_000_000) +
            b'</w:t></w:r></w:p></w:body></w:document>'
        )
        with self.assertRaises(ValueError):
            parse_document("zipbomb.docx", make_docx(xml))

    def test_docx_archive_entry_count_is_bounded(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("word/document.xml", b"<root/>")
            for index in range(256):
                archive.writestr(f"extra/{index}.txt", b"x")
        with self.assertRaises(ValueError):
            parse_document("many.docx", stream.getvalue())

    def test_pdf_signature_is_required(self):
        with self.assertRaises(ValueError):
            parse_document("fake.pdf", b"not a pdf")

    def test_encrypted_pdf_is_rejected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.encrypt("secret")
        stream = io.BytesIO()
        writer.write(stream)
        with self.assertRaises(ValueError):
            parse_document("encrypted.pdf", stream.getvalue())

    def test_pdf_page_limit_is_enforced_before_text_extraction(self):
        writer = PdfWriter()
        for _ in range(101):
            writer.add_blank_page(width=72, height=72)
        stream = io.BytesIO()
        writer.write(stream)
        with self.assertRaises(ValueError):
            parse_document("many-pages.pdf", stream.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
