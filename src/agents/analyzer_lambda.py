"""
AWS Lambda handler for the Analyzer Agent.
Handles deep analysis of Sources Sought opportunities.
"""

import json
import asyncio
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError

from .analyzer import AnalyzerAgent
from ..core.agent_base import AgentContext
from ..utils.logger import get_logger, report_error

logger = get_logger("analyzer_lambda")

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for the Analyzer Agent.
    
    Processes opportunities for detailed analysis including:
    - Requirement extraction and analysis
    - Gap analysis against company capabilities
    - Win probability assessment
    - Strategic recommendations
    """
    
    try:
        # Run the async handler
        return asyncio.run(async_handler(event, context))
        
    except Exception as e:
        logger.error(f"Lambda handler failed: {e}")
        report_error(
            f"Analyzer Lambda failed: {str(e)}",
            {"event": event, "context": str(context)},
            getattr(context, 'aws_request_id', None)
        )
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Internal server error",
                "message": str(e)
            })
        }

async def async_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Async handler for the Analyzer Agent"""
    
    logger.info(f"Analyzer Lambda invoked with event: {json.dumps(event, default=str)}")
    
    # Initialize the agent
    agent = AnalyzerAgent()
    
    # Extract task data from event
    task_data = {}
    
    if "Records" in event:
        # SQS triggered
        for record in event["Records"]:
            if record.get("eventSource") == "aws:sqs":
                try:
                    message_body = json.loads(record["body"])
                    task_data = message_body.get("data", message_body)
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse SQS message: {e}")
                    continue
    else:
        # Direct invocation or API Gateway
        task_data = event
    
    # Create agent context
    agent_context = AgentContext(
        correlation_id=getattr(context, 'aws_request_id', None),
        metadata={
            "trigger": "lambda",
            "event_source": event.get("source", "unknown"),
            "function_name": getattr(context, 'function_name', 'analyzer-agent'),
            "function_version": getattr(context, 'function_version', '$LATEST')
        }
    )
    
    # Validate required parameters
    required_fields = ["action"]
    if not all(field in task_data for field in required_fields):
        missing_fields = [field for field in required_fields if field not in task_data]
        error_msg = f"Missing required fields: {missing_fields}"
        logger.error(error_msg)
        
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Bad Request",
                "message": error_msg,
                "required_fields": required_fields
            })
        }
    
    try:
        # Execute the agent
        logger.info(f"Executing analyzer agent with action: {task_data.get('action')}")
        result = await agent.execute(task_data, agent_context)
        
        if result.success:
            logger.info(f"Analyzer agent completed successfully")
            
            # Send results to downstream agents if needed
            await send_analysis_results(task_data, result.data, agent_context)
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "success": True,
                    "data": result.data,
                    "message": result.message
                }, default=str)
            }
        else:
            logger.error(f"Analyzer agent failed: {result.error}")
            report_error(
                f"Analyzer agent execution failed: {result.error}",
                {"task_data": task_data, "result": result.data},
                agent_context.correlation_id
            )
            
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "success": False,
                    "error": result.error,
                    "message": result.message or "Agent execution failed"
                })
            }
            
    except Exception as e:
        logger.error(f"Analyzer agent execution failed: {e}")
        report_error(
            f"Analyzer agent unexpected error: {str(e)}",
            {"task_data": task_data, "context": str(context)},
            agent_context.correlation_id
        )
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "error": str(e),
                "message": "Agent execution failed with unexpected error"
            })
        }

async def send_analysis_results(task_data: Dict[str, Any], result_data: Dict[str, Any], 
                               context: AgentContext) -> None:
    """Send analysis results to downstream agents based on the decision"""
    
    try:
        action = task_data.get("action")
        opportunity_id = task_data.get("opportunity_id")
        
        if not opportunity_id:
            logger.warning("No opportunity_id provided, skipping downstream notifications")
            return
        
        sqs = boto3.client('sqs')
        
        # Determine next steps based on analysis results
        analysis = result_data.get("analysis", {})
        recommendation = analysis.get("recommendation", "")
        confidence = analysis.get("confidence", 0)
        
        if recommendation.lower() == "bid" and confidence >= 0.6:
            # High confidence bid recommendation - trigger response generation
            await trigger_response_generation(sqs, opportunity_id, analysis, context)
            
        elif recommendation.lower() == "bid" and confidence >= 0.4:
            # Medium confidence - request human approval
            await trigger_human_approval(sqs, opportunity_id, analysis, context)
            
        elif recommendation.lower() == "no-bid":
            # No-bid decision - update relationship manager for future opportunities
            await trigger_relationship_management(sqs, opportunity_id, analysis, context, "no_bid")
            
        else:
            logger.info(f"Analysis complete for {opportunity_id}, no automatic next steps")
            
    except Exception as e:
        logger.error(f"Failed to send analysis results downstream: {e}")

async def trigger_response_generation(sqs: Any, opportunity_id: str, analysis: Dict[str, Any], 
                                    context: AgentContext) -> None:
    """Trigger response generation agent"""
    
    try:
        from ..core.config import config
        
        queue_url = config.get_queue_url("response-generator-queue")
        
        message = {
            "action": "generate_response",
            "opportunity_id": opportunity_id,
            "analysis_results": analysis,
            "priority": "high" if analysis.get("confidence", 0) >= 0.8 else "medium",
            "correlation_id": context.correlation_id,
            "triggered_by": "analyzer_agent",
            "timestamp": analysis.get("analysis_timestamp")
        }
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message, default=str),
            MessageAttributes={
                'correlation_id': {
                    'StringValue': context.correlation_id or '',
                    'DataType': 'String'
                },
                'priority': {
                    'StringValue': message["priority"],
                    'DataType': 'String'
                }
            }
        )
        
        logger.info(f"Triggered response generation for {opportunity_id}: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"Failed to trigger response generation: {e}")

async def trigger_human_approval(sqs: Any, opportunity_id: str, analysis: Dict[str, Any], 
                               context: AgentContext) -> None:
    """Trigger human approval workflow"""
    
    try:
        from ..core.config import config
        
        queue_url = config.get_queue_url("human-loop-queue")
        
        message = {
            "action": "request_approval",
            "workflow_type": "opportunity_decision",
            "opportunity_id": opportunity_id,
            "analysis_results": analysis,
            "decision_required": "bid_no_bid",
            "urgency": "medium",
            "correlation_id": context.correlation_id,
            "triggered_by": "analyzer_agent",
            "timestamp": analysis.get("analysis_timestamp")
        }
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message, default=str),
            MessageAttributes={
                'correlation_id': {
                    'StringValue': context.correlation_id or '',
                    'DataType': 'String'
                },
                'workflow_type': {
                    'StringValue': 'opportunity_decision',
                    'DataType': 'String'
                }
            }
        )
        
        logger.info(f"Triggered human approval for {opportunity_id}: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"Failed to trigger human approval: {e}")

async def trigger_relationship_management(sqs: Any, opportunity_id: str, analysis: Dict[str, Any], 
                                        context: AgentContext, action_type: str) -> None:
    """Trigger relationship management actions"""
    
    try:
        from ..core.config import config
        
        queue_url = config.get_queue_url("relationship-manager-queue")
        
        message = {
            "action": "manage_relationship",
            "action_type": action_type,
            "opportunity_id": opportunity_id,
            "analysis_results": analysis,
            "correlation_id": context.correlation_id,
            "triggered_by": "analyzer_agent",
            "timestamp": analysis.get("analysis_timestamp")
        }
        
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message, default=str),
            MessageAttributes={
                'correlation_id': {
                    'StringValue': context.correlation_id or '',
                    'DataType': 'String'
                },
                'action_type': {
                    'StringValue': action_type,
                    'DataType': 'String'
                }
            }
        )
        
        logger.info(f"Triggered relationship management for {opportunity_id}: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"Failed to trigger relationship management: {e}")

# Utility function for testing
async def test_analyzer_agent():
    """Test function for local development"""
    
    test_event = {
        "action": "analyze_opportunity",
        "opportunity_id": "test-opp-123",
        "analysis_type": "comprehensive"
    }
    
    class MockContext:
        aws_request_id = "test-request-123"
        function_name = "test-analyzer"
        function_version = "$LATEST"
    
    result = await async_handler(test_event, MockContext())
    print(f"Test result: {json.dumps(result, indent=2)}")

if __name__ == "__main__":
    # Run test when executed directly
    asyncio.run(test_analyzer_agent())