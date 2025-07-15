#!/usr/bin/env python3
"""
GovBiz Database Operations MCP Server

Advanced DynamoDB operations, data modeling, and event sourcing
for the GovBiz AI system.
"""

import asyncio
import json
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError, NoCredentialsError
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
import uuid
from decimal import Decimal
import pandas as pd

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class DynamoDBManager:
    """Enhanced DynamoDB operations manager"""
    
    def __init__(self, region_name: str = "us-east-1"):
        self.region_name = region_name
        self.session = boto3.Session()
        self.dynamodb = self.session.resource('dynamodb', region_name=region_name)
        self.client = self.session.client('dynamodb', region_name=region_name)
        
        # Table configurations
        self.table_configs = {
            "opportunities": {
                "table_name": "sources-sought-opportunities",
                "partition_key": "notice_id",
                "sort_key": None,
                "gsi": [
                    {"name": "agency-index", "partition_key": "agency", "sort_key": "posted_date"},
                    {"name": "naics-index", "partition_key": "naics_code", "sort_key": "response_deadline"},
                    {"name": "status-index", "partition_key": "active", "sort_key": "posted_date"}
                ]
            },
            "companies": {
                "table_name": "sources-sought-companies",
                "partition_key": "company_id",
                "sort_key": None,
                "gsi": [
                    {"name": "name-index", "partition_key": "company_name", "sort_key": "created_at"}
                ]
            },
            "responses": {
                "table_name": "sources-sought-responses",
                "partition_key": "response_id",
                "sort_key": None,
                "gsi": [
                    {"name": "opportunity-index", "partition_key": "notice_id", "sort_key": "created_at"},
                    {"name": "status-index", "partition_key": "status", "sort_key": "created_at"}
                ]
            },
            "events": {
                "table_name": "sources-sought-events",
                "partition_key": "event_id",
                "sort_key": "timestamp",
                "gsi": [
                    {"name": "entity-index", "partition_key": "entity_id", "sort_key": "timestamp"},
                    {"name": "type-index", "partition_key": "event_type", "sort_key": "timestamp"}
                ]
            },
            "contacts": {
                "table_name": "sources-sought-contacts",
                "partition_key": "contact_id", 
                "sort_key": None,
                "gsi": [
                    {"name": "agency-index", "partition_key": "agency", "sort_key": "last_contact"},
                    {"name": "email-index", "partition_key": "email", "sort_key": "created_at"}
                ]
            },
            "relationships": {
                "table_name": "sources-sought-relationships",
                "partition_key": "relationship_id",
                "sort_key": None,
                "gsi": [
                    {"name": "contact-index", "partition_key": "contact_id", "sort_key": "created_at"},
                    {"name": "opportunity-index", "partition_key": "opportunity_id", "sort_key": "interaction_date"}
                ]
            }
        }
    
    def get_table(self, table_name: str):
        """Get DynamoDB table resource"""
        config = self.table_configs.get(table_name)
        if not config:
            raise ValueError(f"Unknown table: {table_name}")
        return self.dynamodb.Table(config["table_name"])
    
    def _convert_decimals(self, obj):
        """Convert Decimal objects to float for JSON serialization"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_decimals(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_decimals(item) for item in obj]
        return obj
    
    def _prepare_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare item for DynamoDB storage"""
        # Add timestamps
        now = datetime.now().isoformat()
        if "created_at" not in item:
            item["created_at"] = now
        item["updated_at"] = now
        
        # Convert float to Decimal for DynamoDB
        def convert_floats(obj):
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, dict):
                return {key: convert_floats(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_floats(item) for item in obj]
            return obj
        
        return convert_floats(item)


class OpportunityManager:
    """Manages sources sought opportunities"""
    
    def __init__(self, db_manager: DynamoDBManager):
        self.db = db_manager
        self.table = db_manager.get_table("opportunities")
    
    async def upsert_opportunity(self, opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update opportunity with event sourcing"""
        
        try:
            # Prepare the item
            item = self.db._prepare_item(opportunity_data.copy())
            
            # Ensure required fields
            if "notice_id" not in item:
                return {"error": "notice_id is required"}
            
            # Check if item exists
            existing_response = self.table.get_item(Key={"notice_id": item["notice_id"]})
            is_update = "Item" in existing_response
            
            # Set status based on dates
            current_date = datetime.now().date()
            if "archive_date" in item:
                try:
                    archive_date = datetime.fromisoformat(item["archive_date"]).date()
                    item["active"] = "active" if current_date >= archive_date else "inactive"
                except:
                    item["active"] = "unknown"
            
            # Store the item
            self.table.put_item(Item=item)
            
            # Create event record
            event_data = {
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "event_type": "opportunity_updated" if is_update else "opportunity_created",
                "entity_id": item["notice_id"],
                "entity_type": "opportunity",
                "changes": item,
                "metadata": {
                    "source": "csv_processor",
                    "is_update": is_update
                }
            }
            
            # Store event
            events_manager = EventManager(self.db)
            await events_manager.create_event(event_data)
            
            return {
                "success": True,
                "notice_id": item["notice_id"],
                "action": "updated" if is_update else "created",
                "active": item.get("active", "unknown"),
                "processed_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "notice_id": opportunity_data.get("notice_id")
            }
    
    async def get_opportunity(self, notice_id: str) -> Dict[str, Any]:
        """Get specific opportunity"""
        
        try:
            response = self.table.get_item(Key={"notice_id": notice_id})
            
            if "Item" in response:
                item = self.db._convert_decimals(response["Item"])
                return {
                    "success": True,
                    "opportunity": item,
                    "found": True
                }
            else:
                return {
                    "success": True,
                    "found": False,
                    "notice_id": notice_id
                }
                
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "notice_id": notice_id
            }
    
    async def search_opportunities(self, filters: Dict[str, Any], limit: int = 50) -> Dict[str, Any]:
        """Search opportunities with advanced filtering"""
        
        try:
            # Determine the best index to use
            query_params = {"Limit": limit}
            
            if "agency" in filters:
                # Use agency index
                query_params["IndexName"] = "agency-index"
                query_params["KeyConditionExpression"] = Key("agency").eq(filters["agency"])
                
                if "posted_date_from" in filters:
                    posted_date = filters["posted_date_from"]
                    query_params["KeyConditionExpression"] &= Key("posted_date").gte(posted_date)
                    
            elif "naics_code" in filters:
                # Use NAICS index
                query_params["IndexName"] = "naics-index"
                query_params["KeyConditionExpression"] = Key("naics_code").eq(filters["naics_code"])
                
            elif "active" in filters:
                # Use status index
                query_params["IndexName"] = "status-index"
                query_params["KeyConditionExpression"] = Key("active").eq(filters["active"])
                
            else:
                # Scan table (less efficient)
                return await self._scan_opportunities(filters, limit)
            
            # Add filter expressions
            filter_conditions = []
            
            if "title_contains" in filters:
                filter_conditions.append(Attr("title").contains(filters["title_contains"]))
            
            if "response_deadline_before" in filters:
                filter_conditions.append(Attr("response_deadline").lte(filters["response_deadline_before"]))
            
            if "set_aside" in filters:
                filter_conditions.append(Attr("set_aside").eq(filters["set_aside"]))
            
            if filter_conditions:
                filter_expr = filter_conditions[0]
                for condition in filter_conditions[1:]:
                    filter_expr &= condition
                query_params["FilterExpression"] = filter_expr
            
            # Execute query
            response = self.table.query(**query_params)
            
            items = [self.db._convert_decimals(item) for item in response.get("Items", [])]
            
            return {
                "success": True,
                "opportunities": items,
                "count": len(items),
                "scanned_count": response.get("ScannedCount", len(items)),
                "last_evaluated_key": response.get("LastEvaluatedKey"),
                "filters_applied": filters
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "filters": filters
            }
    
    async def _scan_opportunities(self, filters: Dict[str, Any], limit: int) -> Dict[str, Any]:
        """Scan table with filters (less efficient fallback)"""
        
        scan_params = {"Limit": limit}
        filter_conditions = []
        
        for key, value in filters.items():
            if key not in ["title_contains", "response_deadline_before"]:
                filter_conditions.append(Attr(key).eq(value))
        
        if "title_contains" in filters:
            filter_conditions.append(Attr("title").contains(filters["title_contains"]))
        
        if "response_deadline_before" in filters:
            filter_conditions.append(Attr("response_deadline").lte(filters["response_deadline_before"]))
        
        if filter_conditions:
            filter_expr = filter_conditions[0]
            for condition in filter_conditions[1:]:
                filter_expr &= condition
            scan_params["FilterExpression"] = filter_expr
        
        response = self.table.scan(**scan_params)
        items = [self.db._convert_decimals(item) for item in response.get("Items", [])]
        
        return {
            "success": True,
            "opportunities": items,
            "count": len(items),
            "scanned_count": response.get("ScannedCount", 0),
            "method": "scan",
            "filters_applied": filters
        }


class EventManager:
    """Manages event sourcing and audit trail"""
    
    def __init__(self, db_manager: DynamoDBManager):
        self.db = db_manager
        self.table = db_manager.get_table("events")
    
    async def create_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new event record"""
        
        try:
            # Prepare event item
            item = self.db._prepare_item(event_data.copy())
            
            # Ensure required fields
            if "event_id" not in item:
                item["event_id"] = str(uuid.uuid4())
            
            if "timestamp" not in item:
                item["timestamp"] = datetime.now().isoformat()
            
            # Store event
            self.table.put_item(Item=item)
            
            return {
                "success": True,
                "event_id": item["event_id"],
                "timestamp": item["timestamp"],
                "stored_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }
    
    async def get_entity_events(self, entity_id: str, limit: int = 100) -> Dict[str, Any]:
        """Get all events for a specific entity"""
        
        try:
            response = self.table.query(
                IndexName="entity-index",
                KeyConditionExpression=Key("entity_id").eq(entity_id),
                ScanIndexForward=False,  # Newest first
                Limit=limit
            )
            
            events = [self.db._convert_decimals(item) for item in response.get("Items", [])]
            
            return {
                "success": True,
                "entity_id": entity_id,
                "events": events,
                "count": len(events),
                "last_evaluated_key": response.get("LastEvaluatedKey")
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "entity_id": entity_id
            }
    
    async def get_events_by_type(self, event_type: str, start_time: str = None, 
                                end_time: str = None, limit: int = 100) -> Dict[str, Any]:
        """Get events by type within time range"""
        
        try:
            query_params = {
                "IndexName": "type-index",
                "KeyConditionExpression": Key("event_type").eq(event_type),
                "ScanIndexForward": False,
                "Limit": limit
            }
            
            if start_time:
                if end_time:
                    query_params["KeyConditionExpression"] &= Key("timestamp").between(start_time, end_time)
                else:
                    query_params["KeyConditionExpression"] &= Key("timestamp").gte(start_time)
            elif end_time:
                query_params["KeyConditionExpression"] &= Key("timestamp").lte(end_time)
            
            response = self.table.query(**query_params)
            events = [self.db._convert_decimals(item) for item in response.get("Items", [])]
            
            return {
                "success": True,
                "event_type": event_type,
                "events": events,
                "count": len(events),
                "time_range": {"start": start_time, "end": end_time}
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "event_type": event_type
            }


class AnalyticsManager:
    """Database analytics and reporting"""
    
    def __init__(self, db_manager: DynamoDBManager):
        self.db = db_manager
    
    async def get_opportunity_stats(self, date_range: Dict[str, str] = None) -> Dict[str, Any]:
        """Get opportunity statistics"""
        
        try:
            opportunities_table = self.db.get_table("opportunities")
            
            # Get all opportunities (or filtered by date)
            if date_range and "start_date" in date_range:
                response = opportunities_table.scan(
                    FilterExpression=Attr("posted_date").gte(date_range["start_date"])
                )
            else:
                response = opportunities_table.scan()
            
            opportunities = response.get("Items", [])
            
            # Calculate statistics
            total_count = len(opportunities)
            active_count = sum(1 for opp in opportunities if opp.get("active") == "active")
            
            # Group by agency
            agency_counts = {}
            naics_counts = {}
            set_aside_counts = {}
            
            for opp in opportunities:
                # Agency stats
                agency = opp.get("agency", "Unknown")
                agency_counts[agency] = agency_counts.get(agency, 0) + 1
                
                # NAICS stats
                naics = opp.get("naics_code", "Unknown")
                naics_counts[naics] = naics_counts.get(naics, 0) + 1
                
                # Set-aside stats
                set_aside = opp.get("set_aside", "None")
                set_aside_counts[set_aside] = set_aside_counts.get(set_aside, 0) + 1
            
            return {
                "success": True,
                "total_opportunities": total_count,
                "active_opportunities": active_count,
                "inactive_opportunities": total_count - active_count,
                "by_agency": dict(sorted(agency_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
                "by_naics": dict(sorted(naics_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
                "by_set_aside": set_aside_counts,
                "date_range": date_range,
                "calculated_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }
    
    async def get_response_stats(self) -> Dict[str, Any]:
        """Get response statistics"""
        
        try:
            responses_table = self.db.get_table("responses")
            response = responses_table.scan()
            
            responses = response.get("Items", [])
            
            # Calculate statistics
            total_responses = len(responses)
            status_counts = {}
            
            for resp in responses:
                status = resp.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "success": True,
                "total_responses": total_responses,
                "by_status": status_counts,
                "calculated_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }


class DataExportManager:
    """Data export and backup utilities"""
    
    def __init__(self, db_manager: DynamoDBManager):
        self.db = db_manager
    
    async def export_table_to_json(self, table_name: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Export table data to JSON format"""
        
        try:
            table = self.db.get_table(table_name)
            
            if filters:
                # Apply filters using scan
                scan_params = {}
                filter_conditions = []
                
                for key, value in filters.items():
                    filter_conditions.append(Attr(key).eq(value))
                
                if filter_conditions:
                    filter_expr = filter_conditions[0]
                    for condition in filter_conditions[1:]:
                        filter_expr &= condition
                    scan_params["FilterExpression"] = filter_expr
                
                response = table.scan(**scan_params)
            else:
                response = table.scan()
            
            items = [self.db._convert_decimals(item) for item in response.get("Items", [])]
            
            export_data = {
                "table_name": table_name,
                "exported_at": datetime.now().isoformat(),
                "item_count": len(items),
                "filters_applied": filters,
                "data": items
            }
            
            return {
                "success": True,
                "export_data": export_data,
                "size_mb": len(json.dumps(export_data)) / (1024 * 1024)
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "table_name": table_name
            }


# Initialize the MCP server
server = Server("govbiz-database-mcp")

# Initialize database services
db_manager = DynamoDBManager()
opportunity_manager = OpportunityManager(db_manager)
event_manager = EventManager(db_manager)
analytics_manager = AnalyticsManager(db_manager)
export_manager = DataExportManager(db_manager)

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available database resources"""
    
    resources = [
        Resource(
            uri="database://schemas",
            name="Database Schemas",
            description="DynamoDB table schemas and configurations",
            mimeType="application/json"
        ),
        Resource(
            uri="database://indexes",
            name="Database Indexes",
            description="Global Secondary Index configurations",
            mimeType="application/json"
        ),
        Resource(
            uri="database://analytics",
            name="Analytics Queries",
            description="Predefined analytics queries and reports",
            mimeType="application/json"
        ),
        Resource(
            uri="database://event-types",
            name="Event Types",
            description="Event sourcing event type definitions",
            mimeType="application/json"
        ),
        Resource(
            uri="database://best-practices",
            name="Database Best Practices",
            description="DynamoDB best practices for Sources Sought AI",
            mimeType="text/markdown"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read database resource content"""
    
    if uri == "database://schemas":
        return json.dumps(db_manager.table_configs, indent=2)
    
    elif uri == "database://indexes":
        indexes = {}
        for table_name, config in db_manager.table_configs.items():
            indexes[table_name] = {
                "primary_key": {
                    "partition_key": config["partition_key"],
                    "sort_key": config["sort_key"]
                },
                "global_secondary_indexes": config.get("gsi", [])
            }
        return json.dumps(indexes, indent=2)
    
    elif uri == "database://analytics":
        analytics_queries = {
            "opportunity_trends": {
                "description": "Track opportunity trends over time",
                "query_type": "time_series",
                "example": "get_opportunity_stats with date_range"
            },
            "agency_performance": {
                "description": "Analyze performance by agency",
                "query_type": "aggregation",
                "example": "group opportunities by agency"
            },
            "response_rates": {
                "description": "Calculate response success rates",
                "query_type": "metric",
                "example": "responses submitted vs opportunities found"
            },
            "naics_analysis": {
                "description": "Analyze opportunities by NAICS codes",
                "query_type": "categorical",
                "example": "group by naics_code and count"
            }
        }
        return json.dumps(analytics_queries, indent=2)
    
    elif uri == "database://event-types":
        event_types = {
            "opportunity_created": {
                "description": "New opportunity discovered",
                "entity_type": "opportunity",
                "required_fields": ["notice_id", "source"]
            },
            "opportunity_updated": {
                "description": "Existing opportunity modified",
                "entity_type": "opportunity", 
                "required_fields": ["notice_id", "changes"]
            },
            "response_generated": {
                "description": "AI response generated",
                "entity_type": "response",
                "required_fields": ["response_id", "opportunity_id"]
            },
            "response_submitted": {
                "description": "Response submitted to government",
                "entity_type": "response",
                "required_fields": ["response_id", "submission_method"]
            },
            "email_received": {
                "description": "Email received from government",
                "entity_type": "email",
                "required_fields": ["email_id", "sender", "subject"]
            },
            "email_sent": {
                "description": "Email sent to government",
                "entity_type": "email",
                "required_fields": ["email_id", "recipient", "subject"]
            },
            "contact_created": {
                "description": "New government contact added",
                "entity_type": "contact",
                "required_fields": ["contact_id", "agency"]
            },
            "relationship_updated": {
                "description": "Contact relationship modified",
                "entity_type": "relationship",
                "required_fields": ["contact_id", "interaction_type"]
            }
        }
        return json.dumps(event_types, indent=2)
    
    elif uri == "database://best-practices":
        best_practices = """# DynamoDB Best Practices for Sources Sought AI

## Data Modeling

### 1. Single Table Design
- Use a single table per service when possible
- Leverage composite keys for relationships
- Use Global Secondary Indexes (GSI) for alternate access patterns

### 2. Partition Key Design
- Choose high-cardinality partition keys
- Avoid hot partitions by distributing load evenly
- Use meaningful, predictable key patterns

### 3. Sort Key Strategies
- Use sort keys for range queries and sorting
- Implement hierarchical data with sort key prefixes
- Enable efficient pagination with sort keys

## Performance Optimization

### 1. Read Patterns
- Use Query operations instead of Scan when possible
- Implement pagination for large result sets
- Cache frequently accessed data

### 2. Write Patterns
- Batch write operations when possible
- Use conditional writes to prevent conflicts
- Implement eventual consistency for non-critical reads

### 3. Index Usage
- Create GSIs for alternate query patterns
- Project only necessary attributes to reduce storage costs
- Monitor index usage and remove unused indexes

## Event Sourcing

### 1. Event Structure
- Include event ID, timestamp, and entity ID
- Store complete state changes in event data
- Use consistent event naming conventions

### 2. Event Ordering
- Use timestamps for chronological ordering
- Implement sequence numbers for strict ordering
- Handle clock skew and concurrent events

### 3. Event Replay
- Support event replay for data recovery
- Implement idempotent event processing
- Version event schemas for backward compatibility

## Cost Optimization

### 1. Capacity Planning
- Use on-demand billing for unpredictable workloads
- Monitor and adjust provisioned capacity
- Implement auto-scaling for variable loads

### 2. Storage Optimization
- Remove unnecessary attributes to reduce item size
- Use TTL for automatic data expiration
- Compress large attributes when appropriate

### 3. Request Optimization
- Minimize attribute projections in queries
- Use efficient filter expressions
- Batch operations to reduce request count

## Security

### 1. Access Control
- Use IAM roles with least-privilege access
- Implement fine-grained permissions per table
- Encrypt sensitive data at rest and in transit

### 2. Data Protection
- Use VPC endpoints for private access
- Enable point-in-time recovery for critical tables
- Implement backup and disaster recovery procedures

## Monitoring

### 1. CloudWatch Metrics
- Monitor read/write capacity utilization
- Track throttling events and error rates
- Set up alarms for performance thresholds

### 2. Application Metrics
- Track business metrics in events table
- Monitor data quality and consistency
- Implement health checks for critical operations

## Error Handling

### 1. Retry Logic
- Implement exponential backoff for throttling
- Handle eventual consistency in read operations
- Use circuit breakers for external dependencies

### 2. Data Validation
- Validate data before writing to tables
- Implement schema validation for events
- Handle malformed or incomplete data gracefully

## Backup and Recovery

### 1. Backup Strategy
- Enable continuous backups for critical tables
- Schedule regular point-in-time backups
- Test backup and restore procedures regularly

### 2. Disaster Recovery
- Replicate critical data across regions
- Implement automated failover procedures
- Document recovery time and point objectives
"""
        return best_practices
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available database tools"""
    
    tools = [
        Tool(
            name="upsert_opportunity",
            description="Insert or update opportunity with event sourcing",
            inputSchema={
                "type": "object",
                "properties": {
                    "opportunity_data": {"type": "object", "description": "Opportunity data to store"}
                },
                "required": ["opportunity_data"]
            }
        ),
        Tool(
            name="get_opportunity",
            description="Get specific opportunity by notice ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "notice_id": {"type": "string", "description": "Notice ID to retrieve"}
                },
                "required": ["notice_id"]
            }
        ),
        Tool(
            name="search_opportunities",
            description="Search opportunities with advanced filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "filters": {"type": "object", "description": "Search filters"},
                    "limit": {"type": "integer", "description": "Maximum results", "default": 50}
                },
                "required": ["filters"]
            }
        ),
        Tool(
            name="create_event",
            description="Create event sourcing record",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_data": {"type": "object", "description": "Event data to store"}
                },
                "required": ["event_data"]
            }
        ),
        Tool(
            name="get_entity_events",
            description="Get all events for a specific entity",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity ID to get events for"},
                    "limit": {"type": "integer", "description": "Maximum events", "default": 100}
                },
                "required": ["entity_id"]
            }
        ),
        Tool(
            name="get_events_by_type",
            description="Get events by type within time range",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_type": {"type": "string", "description": "Event type to filter by"},
                    "start_time": {"type": "string", "description": "Start time (ISO format)"},
                    "end_time": {"type": "string", "description": "End time (ISO format)"},
                    "limit": {"type": "integer", "description": "Maximum events", "default": 100}
                },
                "required": ["event_type"]
            }
        ),
        Tool(
            name="get_opportunity_stats",
            description="Get opportunity analytics and statistics",
            inputSchema={
                "type": "object",
                "properties": {
                    "date_range": {"type": "object", "description": "Date range filter"}
                }
            }
        ),
        Tool(
            name="get_response_stats",
            description="Get response analytics and statistics",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="export_table_data",
            description="Export table data to JSON format",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Table to export"},
                    "filters": {"type": "object", "description": "Export filters"}
                },
                "required": ["table_name"]
            }
        ),
        Tool(
            name="batch_operation",
            description="Perform batch read or write operations",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "description": "Operation type", "enum": ["batch_get", "batch_write"]},
                    "table_name": {"type": "string", "description": "Table name"},
                    "items": {"type": "array", "description": "Items for operation"}
                },
                "required": ["operation", "table_name", "items"]
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "upsert_opportunity":
        result = await opportunity_manager.upsert_opportunity(
            opportunity_data=arguments["opportunity_data"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_opportunity":
        result = await opportunity_manager.get_opportunity(
            notice_id=arguments["notice_id"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "search_opportunities":
        result = await opportunity_manager.search_opportunities(
            filters=arguments["filters"],
            limit=arguments.get("limit", 50)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "create_event":
        result = await event_manager.create_event(
            event_data=arguments["event_data"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_entity_events":
        result = await event_manager.get_entity_events(
            entity_id=arguments["entity_id"],
            limit=arguments.get("limit", 100)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_events_by_type":
        result = await event_manager.get_events_by_type(
            event_type=arguments["event_type"],
            start_time=arguments.get("start_time"),
            end_time=arguments.get("end_time"),
            limit=arguments.get("limit", 100)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_opportunity_stats":
        result = await analytics_manager.get_opportunity_stats(
            date_range=arguments.get("date_range")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_response_stats":
        result = await analytics_manager.get_response_stats()
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "export_table_data":
        result = await export_manager.export_table_to_json(
            table_name=arguments["table_name"],
            filters=arguments.get("filters")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "batch_operation":
        # Implement batch operations
        operation = arguments["operation"]
        table_name = arguments["table_name"] 
        items = arguments["items"]
        
        try:
            table = db_manager.get_table(table_name)
            
            if operation == "batch_write":
                # Batch write operation
                with table.batch_writer() as batch:
                    for item in items:
                        prepared_item = db_manager._prepare_item(item)
                        batch.put_item(Item=prepared_item)
                
                result = {
                    "success": True,
                    "operation": "batch_write",
                    "items_written": len(items),
                    "table_name": table_name
                }
            
            elif operation == "batch_get":
                # Batch get operation (simplified)
                results = []
                for key_item in items:
                    response = table.get_item(Key=key_item)
                    if "Item" in response:
                        results.append(db_manager._convert_decimals(response["Item"]))
                
                result = {
                    "success": True,
                    "operation": "batch_get",
                    "items_requested": len(items),
                    "items_found": len(results),
                    "items": results
                }
            
            else:
                result = {"error": f"Unknown batch operation: {operation}"}
            
        except ClientError as e:
            result = {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "operation": operation
            }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Run the MCP server"""
    
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializeResult(
                protocolVersion="2024-11-05",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())