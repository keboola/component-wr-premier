import unittest
from pathlib import Path

from keboola.datadirtest.vcr import VCRDataDirTester

FUNCTIONAL_DIR = Path(__file__).resolve().parent / "functional"
COMPONENT_SCRIPT = Path(__file__).resolve().parent.parent / "src" / "component.py"


class TestFunctional(unittest.TestCase):
    def test_functional(self):
        tester = VCRDataDirTester(
            data_dir=str(FUNCTIONAL_DIR),
            component_script=str(COMPONENT_SCRIPT),
        )
        tester.run()


if __name__ == "__main__":
    unittest.main()
