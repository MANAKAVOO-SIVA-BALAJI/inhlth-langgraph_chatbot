from typing import List , Literal
from langchain.tools import tool
from graphql_memory import HasuraMemory
from config import HASURA_ADMIN_SECRET ,HASURA_GRAPHQL_URL,HASURA_ROLE
from context_store import get_user_id
graphql_client = HasuraMemory(
    hasura_url=HASURA_GRAPHQL_URL,
    hasura_secret=HASURA_ADMIN_SECRET,
    hasura_role=HASURA_ROLE,
    user_id=get_user_id()
)
@tool
def get_order_details_by_ids(order_ids: list[str]):
    """
    Get the complete details of multiple orders by their request IDs.
    Useful when users mention multiple order IDs in one message.
    """
    name = "get_order_details_by_ids"
    description = "Get detailed order info for one or more order IDs (request_id)"

    query = """
    query GetOrdersByIds($order_ids: [String!]!) {
      bloodorderview(where: {request_id: {_in: $order_ids}}) {
        request_id
        status
        blood_group
        creation_date_and_time
        delivery_date_and_time
        reason
        patient_id
        first_name
        last_name
        order_line_items
        blood_bank_name
      }
    }
    """
    variables = {"order_ids": order_ids}
    result = graphql_client.run_query(query, variables)
    return result


@tool
def get_orders_by_statuses(statuses: list[str], limit: int = 5, offset: int = 0):
    """
    Fetch orders filtered by their status codes.
    Supports multiple statuses and pagination.
    """
    name = "get_orders_by_statuses"
    description = "Fetch orders based on multiple status codes like CMP, PA, CAL, etc."

    query = """
    query GetOrdersByStatuses($statuses: [orderstatusenum!]!, $limit: Int = 5, $offset: Int = 0) {
      bloodorderview(
        where: {status: {_in: $statuses}},
        limit: $limit,
        offset: $offset
      ) {
        request_id
        status
        creation_date_and_time
        first_name
        last_name
      }
    }
    """
    variables = {"statuses": statuses, "limit": limit, "offset": offset}
    result = graphql_client.run_query(query, variables)
    return result


@tool
def get_current_orders_data(limit: int = 5, offset: int = 0):
    """
    Get current active orders (excluding completed, rejected, or cancelled).
    Used for general list display or pagination.
    """
    name = "get_current_orders_data"
    description = "List active orders (not completed, rejected, or cancelled). Supports pagination."

    query = """
    query GetCurrentOrders($limit: Int = 5, $offset: Int = 0) {
      bloodorderview(
        where: {status: {_nin: ["CMP", "REJ", "CAL"]}},
        limit: $limit,
        offset: $offset
      ) {
        request_id
        status
        creation_date_and_time
        first_name
        last_name
      }
    }
    """
    variables = {"limit": limit, "offset": offset}
    result = graphql_client.run_query(query, variables)
    return result


@tool
def get_monthly_billing(months: list[str]):
    """
    Get billing data for one or more months. Includes total cost, units used, and patient count.
    """
    name = "get_monthly_billing"
    description = "Fetch total cost, blood units, and patient counts for specific months like ['04-2025']"

    query = """
    query BillingData($months: [String!]!) {
      costandbillingview(where: {month_year: {_in: $months}}) {
        company_name
        month_year
        total_cost
        overall_blood_unit
        total_patient
        blood_component
      }
    }
    """
    variables = {"months": months}
    result = graphql_client.run_query(query, variables)
    return result


@tool
def get_blood_usage_summary(statuses: list[str]):
    """
    Get aggregate blood usage statistics for one or more status codes.
    Useful for summarizing data across statuses like CMP, PA, AA.
    """
    name = "get_blood_usage_summary"
    description = "Summarize blood usage across status codes. Shows blood groups, reasons, and counts."

    query = """
    query BloodUsageSummary($statuses: [orderstatusenum!]!) {
      bloodorderview_aggregate(where: {status: {_in: $statuses}}) {
        aggregate {
          count
        }
        nodes {
          blood_group
          status
          reason
        }
      }
    }
    """
    variables = {"statuses": statuses}
    result = graphql_client.run_query(query, variables)
    return result


@tool
def get_patient_by_blood_groups(groups: list[str]):
    """
    Retrieve patient information for one or more blood groups.
    Helps find all patients with specific blood types.
    """
    name = "get_patient_by_blood_groups"
    description = "Search patients based on one or more blood groups like ['A+', 'B-']."

    query = """
    query GetPatientsByBloodGroup($groups: [String!]!) {
      bloodorderview(where: {blood_group: {_in: $groups}}) {
        first_name
        last_name
        blood_group
        request_id
        status
      }
    }
    """
    variables = {"groups": groups}
    result = graphql_client.run_query(query, variables)
    return result


@tool
def get_recent_order_ids(limit: int = 5):
    """
    Provide a list of recent order IDs. Useful when users input invalid IDs or ask for suggestions.
    """
    name = "get_recent_order_ids"
    description = "List the most recent order IDs. Used when users need to see available orders."

    query = """
    query GetRecentOrderIds($limit: Int = 5) {
      bloodorderview(order_by: {creation_date_and_time: desc}, limit: $limit) {
        request_id
        creation_date_and_time
      }
    }
    """
    variables = {"limit": limit}
    result = graphql_client.run_query(query, variables)
    return result


tools = [get_order_details_by_ids,get_orders_by_statuses,get_current_orders_data,get_monthly_billing,get_patient_by_blood_groups,get_recent_order_ids]

from langgraph.prebuilt import ToolNode, tools_condition

tool_node = ToolNode(tools=tools)