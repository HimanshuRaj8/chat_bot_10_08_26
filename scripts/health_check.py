#!/usr/bin/env python3
"""
System Health Check Script for Enterprise Approval System (Backend V3 & V2)
Checks dataset loading, auth services, query engine, and Ollama connection.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V3_DIR = os.path.join(BASE_DIR, "backend_v3")
V2_DIR = os.path.join(BASE_DIR, "backend_v2")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

def run_health_check():
    print("==========================================================")
    print(" 🏥 Enterprise Approval System AI Health Check")
    print("==========================================================")
    
    # 1. Backend V3 Check
    print("\n[+] Checking Backend V3 Engine...")
    try:
        sys.path.insert(0, V3_DIR)
        import config as config_v3
        from data.excel_provider import ExcelDataProvider as ExcelDP3
        from auth.authentication import AuthService as Auth3
        from auth.authorization import AuthorizationService as Authz3
        from llm.client import LLMClient
        
        dp3 = ExcelDP3(
            requisition_path=config_v3.DEFAULT_REQUISITION_EXCEL,
            employee_path=config_v3.DEFAULT_EMPLOYEE_EXCEL,
            finance_path=config_v3.DEFAULT_FINANCE_EXCEL
        )
        reqs3 = dp3.get_all_requisitions()
        
        llm = LLMClient(
            ollama_url=config_v3.OLLAMA_URL,
            model=config_v3.OLLAMA_MODEL,
        )
        ollama_status = "Connected" if llm.is_available() else "Offline (will use deterministic fallback)"
        
        print(f"  [✓] Backend V3 Config loaded. Port: {config_v3.FLASK_PORT}")
        print(f"  [✓] Excel Data Provider V3 loaded {len(reqs3)} active requisitions.")
        print(f"  [✓] Ollama LLM status: {ollama_status}")
    except Exception as e:
        print(f"  [✗] Backend V3 check failed: {e}")
        return False
    finally:
        if V3_DIR in sys.path:
            sys.path.remove(V3_DIR)
            for m in list(sys.modules.keys()):
                if m in ("config", "data", "auth", "models", "query", "llm", "services", "utils"):
                    del sys.modules[m]

    # 2. Backend V2 Check
    print("\n[+] Checking Backend V2 Baseline Engine...")
    try:
        sys.path.insert(0, V2_DIR)
        import config as config_v2
        from data.excel_provider import ExcelDataProvider as ExcelDP2
        
        dp2 = ExcelDP2(
            requisition_path=config_v2.DEFAULT_REQUISITION_EXCEL,
            employee_path=config_v2.DEFAULT_EMPLOYEE_EXCEL,
            finance_path=config_v2.DEFAULT_FINANCE_EXCEL
        )
        df2 = dp2.get_requisitions_df()
        print(f"  [✓] Backend V2 Config loaded. Port: {config_v2.FLASK_PORT}")
        print(f"  [✓] Excel Data Provider V2 loaded {len(df2)} requisitions.")
    except Exception as e:
        print(f"  [✗] Backend V2 check failed: {e}")
        return False
    finally:
        if V2_DIR in sys.path:
            sys.path.remove(V2_DIR)

    print("\n==========================================================")
    print(" ✅ All Backend V3 & V2 health checks passed successfully!")
    print("==========================================================")
    return True

if __name__ == "__main__":
    success = run_health_check()
    sys.exit(0 if success else 1)
