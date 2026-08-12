import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


OFFICE_ROOT = Path(__file__).parents[1] / "scripts" / "office"
sys.path.insert(0, str(OFFICE_ROOT))


def load_base_validator():
    module_name = f"docx_ooxml_base_{id(OFFICE_ROOT)}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        OFFICE_ROOT / "validators" / "base.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.BaseSchemaValidator


BaseSchemaValidator = load_base_validator()


class OoxmlUtf8ValidationTests(unittest.TestCase):
    def test_schema_validation_opens_utf8_ooxml_explicitly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema_path = root / "schema.xsd"
            xml_path = root / "sample.xml"
            schema_path.write_text(
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<xs:schema xmlns:xs=\"http://www.w3.org/2001/XMLSchema\">
  <xs:element name=\"root\" type=\"xs:string\"/>
</xs:schema>
""",
                encoding="utf-8",
            )
            xml_path.write_text(
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?><root>\\u4e2d\\u6587\\U0001f600</root>",
                encoding="utf-8",
            )

            validator = BaseSchemaValidator(root)
            with patch("builtins.open", wraps=open) as mocked_open:
                valid, errors = validator._validate_single_file_xsd(
                    xml_path,
                    root,
                    schema_path=schema_path,
                )

            self.assertTrue(valid, errors)
            self.assertTrue(
                any(
                    call.args[:2] == (xml_path, "r")
                    and call.kwargs.get("encoding") == "utf-8"
                    for call in mocked_open.call_args_list
                )
            )


if __name__ == "__main__":
    unittest.main()
