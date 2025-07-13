"""
Pytest configuration and shared fixtures for Sources Sought AI tests.
"""

import asyncio
import pytest
import boto3
from moto import mock_dynamodb, mock_s3, mock_sqs
import os
from pathlib import Path
import sys

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.config import config
from src.utils.logger import get_logger


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def mock_dynamodb_table(mock_aws_credentials):
    """Create a mock DynamoDB table for testing."""
    with mock_dynamodb():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        
        # Create opportunities table
        table = dynamodb.create_table(
            TableName="test-opportunities",
            KeySchema=[
                {"AttributeName": "id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        
        yield table


@pytest.fixture
def mock_s3_bucket(mock_aws_credentials):
    """Create a mock S3 bucket for testing."""
    with mock_s3():
        s3 = boto3.client("s3", region_name="us-east-1")
        bucket_name = "test-search-indices"
        s3.create_bucket(Bucket=bucket_name)
        yield bucket_name


@pytest.fixture
def mock_sqs_queue(mock_aws_credentials):
    """Create a mock SQS queue for testing."""
    with mock_sqs():
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue_url = sqs.create_queue(QueueName="test-agent-queue")["QueueUrl"]
        yield queue_url


@pytest.fixture
def sample_opportunity():
    """Sample Sources Sought opportunity data for testing."""
    return {
        "id": "test-opp-001",
        "title": "IT Services for Veterans Affairs",
        "description": "The Department of Veterans Affairs seeks IT services including cloud migration, cybersecurity, and software development.",
        "agency": "Department of Veterans Affairs",
        "notice_id": "36C10B21Q0042",
        "posted_date": "2024-01-15",
        "response_date": "2024-02-15",
        "naics_codes": ["541511", "541512"],
        "place_of_performance": "Washington, DC",
        "set_aside": "Small Business",
        "contact_info": {
            "name": "John Smith",
            "email": "john.smith@va.gov",
            "phone": "202-555-0123"
        },
        "requirements": [
            {
                "title": "Cloud Migration Services",
                "description": "Migrate legacy systems to AWS cloud infrastructure",
                "keywords": ["AWS", "cloud", "migration", "DevOps"]
            },
            {
                "title": "Cybersecurity Implementation",
                "description": "Implement NIST cybersecurity framework",
                "keywords": ["NIST", "cybersecurity", "compliance", "security"]
            }
        ],
        "estimated_value": 5000000,
        "status": "active",
        "match_score": 85.5,
        "priority": "high"
    }


@pytest.fixture
def sample_company():
    """Sample company data for testing."""
    return {
        "id": "test-company-001",
        "name": "TechSolutions Inc",
        "uei": "ABC123DEF456",
        "cage_code": "1A2B3",
        "duns": "123456789",
        "address": {
            "street": "123 Tech Street",
            "city": "Arlington",
            "state": "VA",
            "zip": "22201"
        },
        "certifications": ["small_business", "sdvosb"],
        "naics_codes": ["541511", "541512", "541519"],
        "capabilities": [
            "Cloud Computing",
            "Cybersecurity",
            "Software Development",
            "DevOps"
        ],
        "past_performance": [
            {
                "contract_number": "W52P1J-20-D-0042",
                "customer": "US Army",
                "value": 2500000,
                "period": "2020-2023",
                "description": "IT modernization services"
            }
        ]
    }


@pytest.fixture
def sample_contact():
    """Sample government contact data for testing."""
    return {
        "id": "test-contact-001",
        "first_name": "Jane",
        "last_name": "Doe",
        "title": "Contracting Officer",
        "email": "jane.doe@gsa.gov",
        "phone": "202-555-0456",
        "agency": "General Services Administration",
        "department": "Federal Acquisition Service",
        "organization": "GSA",
        "expertise_areas": ["IT Services", "Cloud Computing"],
        "contact_type": "primary",
        "relationship_strength": 3,
        "last_contact": "2024-01-10",
        "notes": "Primary contact for IT services acquisitions"
    }


@pytest.fixture
def sample_response():
    """Sample Sources Sought response data for testing."""
    return {
        "id": "test-response-001",
        "opportunity_id": "test-opp-001",
        "company_id": "test-company-001",
        "template_type": "professional_services",
        "status": "draft",
        "content": "This is a sample response content...",
        "sections": [
            {
                "title": "Company Information",
                "content": "TechSolutions Inc is a small business..."
            },
            {
                "title": "Relevant Experience", 
                "content": "We have extensive experience in..."
            }
        ],
        "compliance_score": 95,
        "word_count": 1500,
        "created_at": "2024-01-16T10:00:00Z",
        "review_comments": "",
        "approval_status": "pending"
    }


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response for testing."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1677652288,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test AI response for Sources Sought analysis."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
    }


@pytest.fixture
def mock_slack_client():
    """Mock Slack client for testing."""
    class MockSlackClient:
        def __init__(self):
            self.sent_messages = []
        
        async def chat_postMessage(self, **kwargs):
            self.sent_messages.append(kwargs)
            return {
                "ok": True,
                "ts": "1234567890.123456"
            }
        
        async def reactions_add(self, **kwargs):
            return {"ok": True}
    
    return MockSlackClient()


@pytest.fixture
def test_config():
    """Test configuration overrides."""
    original_env = config.environment
    config.environment = "test"
    config.aws.dynamodb_endpoint_url = "http://localhost:8000"
    config.aws.s3_endpoint_url = "http://localhost:4566"
    
    yield config
    
    config.environment = original_env


@pytest.fixture
def logger():
    """Test logger instance."""
    return get_logger("test")