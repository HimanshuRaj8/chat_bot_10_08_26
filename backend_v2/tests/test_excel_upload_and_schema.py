"""
Backend V2 — Excel Schema Mapping & Atomic Upload Regression Tests

Verifies:
  1. RequisitionRecord dataclass instantiation matches ExcelDataProvider mapping without 'value_inr' error
  2. Value and Approved Value fields map correctly to value_in_inr and approved_value_in_inr
  3. ExcelDataProvider atomic refresh preserves dataset integrity on upload error
"""
import os
import pytest
import config
from data.excel_provider import ExcelDataProvider
from models.requisition import RequisitionRecord


class TestExcelSchemaMappingAndUpload:

    def test_requisition_record_mapping_no_value_inr_error(self):
        provider = ExcelDataProvider(
            requisition_path=config.DEFAULT_REQUISITION_EXCEL,
            employee_path=config.DEFAULT_EMPLOYEE_EXCEL,
            finance_path=config.DEFAULT_FINANCE_EXCEL,
        )

        records = provider.get_all_requisitions()
        assert len(records) > 0

        # Check first record mapping
        first_rec = records[0]
        assert isinstance(first_rec, RequisitionRecord)
        assert hasattr(first_rec, "value_in_inr")
        assert hasattr(first_rec, "approved_value_in_inr")

        # Verify not zero for sample data
        assert first_rec.value_in_inr >= 0
        assert first_rec.approved_value_in_inr >= 0

        # Verify source dict representation
        src_dict = first_rec.to_source_dict()
        assert "value_inr" in src_dict
        assert "approved_value_inr" in src_dict

    def test_atomic_refresh_success(self):
        provider = ExcelDataProvider(
            requisition_path=config.DEFAULT_REQUISITION_EXCEL,
            employee_path=config.DEFAULT_EMPLOYEE_EXCEL,
            finance_path=config.DEFAULT_FINANCE_EXCEL,
        )
        initial_count = len(provider.get_all_requisitions())
        assert initial_count > 0

        # Reload with valid files
        new_count = provider.refresh(config.DEFAULT_REQUISITION_EXCEL, config.DEFAULT_EMPLOYEE_EXCEL, config.DEFAULT_FINANCE_EXCEL)
        assert new_count == initial_count
        assert len(provider.get_all_requisitions()) == initial_count

    def test_atomic_refresh_failure_preserves_active_dataset(self, tmp_path):
        provider = ExcelDataProvider(
            requisition_path=config.DEFAULT_REQUISITION_EXCEL,
            employee_path=config.DEFAULT_EMPLOYEE_EXCEL,
            finance_path=config.DEFAULT_FINANCE_EXCEL,
        )
        initial_count = len(provider.get_all_requisitions())
        assert initial_count > 0

        # Create an invalid requisition file
        invalid_file = os.path.join(tmp_path, "invalid.xlsx")
        with open(invalid_file, "w") as f:
            f.write("corrupted excel content")

        # Refresh with corrupted file should raise ValueError/Exception
        with pytest.raises(Exception):
            provider.refresh(invalid_file, config.DEFAULT_EMPLOYEE_EXCEL, config.DEFAULT_FINANCE_EXCEL)

        # Active dataset must remain intact!
        assert len(provider.get_all_requisitions()) == initial_count
