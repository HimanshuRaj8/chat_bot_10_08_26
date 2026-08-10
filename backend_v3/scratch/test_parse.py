import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from query.parser import QueryParser
from llm.client import LLMClient
from models.user import CurrentUser, UserRole

llm_client = LLMClient(ollama_url="http://localhost:11434/api/generate", model="qwen2.5:3b")
parser = QueryParser(llm_client)

user = CurrentUser(employee_id="MI0168", employee_name="Rahul Karn", email="rahul.karn@motherson.com", role=UserRole.EMPLOYEE)
plan = parser.parse_query("total approved value", user)
print("PLAN INTENT:", plan.intent)
print("PLAN METRIC:", plan.metric)
print("PLAN AGGREGATION:", plan.aggregation)
print("PLAN SUBJECT SCOPE:", plan.subject_scope)
print("PLAN TARGET EMPLOYEE ID:", plan.target_employee_id)
