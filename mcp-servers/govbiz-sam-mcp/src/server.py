#!/usr/bin/env python3
"""
GovBiz SAM.gov MCP Server

Provides access to SAM.gov contract opportunity data, NAICS codes, and agency information.
Handles CSV downloads, opportunity search, and government contracting metadata.
"""

import asyncio
import json
import csv
import io
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import re
from pathlib import Path
import gzip

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class SAMDataService:
    """Service for interacting with SAM.gov data"""
    
    def __init__(self):
        self.csv_url = "https://s3.amazonaws.com/falextracts/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv"
        self.api_base = "https://api.sam.gov"
        self.session = None
        
        # CSV column mapping based on CLAUDE.md specification
        self.csv_columns = [
            "NoticeId", "Title", "Sol#", "Department/Ind.Agency", "CGAC", "Sub-Tier",
            "FPDS Code", "Office", "AAC Code", "PostedDate", "Type", "BaseType",
            "ArchiveType", "ArchiveDate", "SetASideCode", "SetASide", "ResponseDeadLine",
            "NaicsCode", "ClassificationCode", "PopStreetAddress", "PopCity", "PopState",
            "PopZip", "PopCountry", "Active", "AwardNumber", "AwardDate", "Award$",
            "Awardee", "PrimaryContactTitle", "PrimaryContactFullname", "PrimaryContactEmail",
            "PrimaryContactPhone", "PrimaryContactFax", "SecondaryContactTitle",
            "SecondaryContactFullname", "SecondaryContactEmail", "SecondaryContactPhone",
            "SecondaryContactFax", "OrganizationType", "State", "City", "ZipCode",
            "CountryCode", "AdditionalInfoLink", "Link", "Description"
        ]
    
    async def _get_session(self):
        """Get or create aiohttp session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def download_csv(self, max_size_mb: int = 500) -> Dict[str, Any]:
        """Download the SAM.gov CSV file"""
        
        session = await self._get_session()
        
        try:
            async with session.get(self.csv_url) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"Failed to download CSV: HTTP {response.status}"
                    }
                
                # Check file size
                content_length = response.headers.get('content-length')
                if content_length:
                    size_mb = int(content_length) / (1024 * 1024)
                    if size_mb > max_size_mb:
                        return {
                            "success": False,
                            "error": f"File too large: {size_mb:.1f}MB (max: {max_size_mb}MB)"
                        }
                
                # Download content
                content = await response.read()
                
                # Handle gzip compression if present
                if response.headers.get('content-encoding') == 'gzip':
                    content = gzip.decompress(content)
                
                csv_text = content.decode('utf-8')
                
                return {
                    "success": True,
                    "size_bytes": len(content),
                    "size_mb": len(content) / (1024 * 1024),
                    "csv_content": csv_text,
                    "downloaded_at": datetime.now().isoformat()
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Download failed: {str(e)}"
            }
    
    async def parse_csv_sample(self, csv_content: str, sample_size: int = 10) -> Dict[str, Any]:
        """Parse a sample of the CSV content"""
        
        try:
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            
            # Get field names
            fieldnames = csv_reader.fieldnames
            
            # Read sample rows
            sample_rows = []
            for i, row in enumerate(csv_reader):
                if i >= sample_size:
                    break
                sample_rows.append(row)
            
            # Get total row count estimate
            total_rows = len(csv_content.split('\n')) - 1  # Subtract header
            
            return {
                "success": True,
                "fieldnames": fieldnames,
                "expected_columns": self.csv_columns,
                "columns_match": fieldnames == self.csv_columns,
                "total_rows_estimate": total_rows,
                "sample_size": len(sample_rows),
                "sample_data": sample_rows
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"CSV parsing failed: {str(e)}"
            }
    
    async def search_opportunities(self, csv_content: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search opportunities in CSV data"""
        
        try:
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            
            matching_opportunities = []
            
            for row in csv_reader:
                # Apply filters
                if self._matches_filters(row, filters):
                    # Clean and structure the data
                    opportunity = self._structure_opportunity(row)
                    matching_opportunities.append(opportunity)
                
                # Limit results
                if len(matching_opportunities) >= filters.get('limit', 100):
                    break
            
            return matching_opportunities
            
        except Exception as e:
            return [{"error": f"Search failed: {str(e)}"}]
    
    def _matches_filters(self, row: Dict[str, str], filters: Dict[str, Any]) -> bool:
        """Check if opportunity matches search filters"""
        
        # Active status filter
        if filters.get('active_only', True):
            if row.get('Active', '').lower() != 'yes':
                return False
        
        # Notice type filter
        if 'notice_type' in filters:
            if row.get('Type', '').lower() != filters['notice_type'].lower():
                return False
        
        # NAICS code filter
        if 'naics_codes' in filters:
            row_naics = row.get('NaicsCode', '')
            if not any(naics in row_naics for naics in filters['naics_codes']):
                return False
        
        # Agency filter
        if 'agencies' in filters:
            agency = row.get('Department/Ind.Agency', '').lower()
            if not any(filter_agency.lower() in agency for filter_agency in filters['agencies']):
                return False
        
        # Set-aside filter
        if 'set_asides' in filters:
            set_aside = row.get('SetAside', '').lower()
            if not any(sa.lower() in set_aside for sa in filters['set_asides']):
                return False
        
        # Keyword search in title and description
        if 'keywords' in filters:
            searchable_text = f"{row.get('Title', '')} {row.get('Description', '')}".lower()
            if not any(keyword.lower() in searchable_text for keyword in filters['keywords']):
                return False
        
        # Date range filter
        if 'posted_after' in filters:
            try:
                posted_date = datetime.strptime(row.get('PostedDate', ''), '%m/%d/%Y')
                filter_date = datetime.strptime(filters['posted_after'], '%Y-%m-%d')
                if posted_date < filter_date:
                    return False
            except:
                pass
        
        return True
    
    def _structure_opportunity(self, row: Dict[str, str]) -> Dict[str, Any]:
        """Structure raw CSV row into clean opportunity object"""
        
        return {
            "notice_id": row.get('NoticeId', ''),
            "title": row.get('Title', ''),
            "solicitation_number": row.get('Sol#', ''),
            "agency": row.get('Department/Ind.Agency', ''),
            "office": row.get('Office', ''),
            "posted_date": row.get('PostedDate', ''),
            "type": row.get('Type', ''),
            "base_type": row.get('BaseType', ''),
            "archive_date": row.get('ArchiveDate', ''),
            "response_deadline": row.get('ResponseDeadLine', ''),
            "naics_code": row.get('NaicsCode', ''),
            "set_aside": row.get('SetAside', ''),
            "set_aside_code": row.get('SetASideCode', ''),
            "place_of_performance": {
                "address": row.get('PopStreetAddress', ''),
                "city": row.get('PopCity', ''),
                "state": row.get('PopState', ''),
                "zip": row.get('PopZip', ''),
                "country": row.get('PopCountry', '')
            },
            "active": row.get('Active', '').lower() == 'yes',
            "primary_contact": {
                "title": row.get('PrimaryContactTitle', ''),
                "name": row.get('PrimaryContactFullname', ''),
                "email": row.get('PrimaryContactEmail', ''),
                "phone": row.get('PrimaryContactPhone', ''),
                "fax": row.get('PrimaryContactFax', '')
            },
            "secondary_contact": {
                "title": row.get('SecondaryContactTitle', ''),
                "name": row.get('SecondaryContactFullname', ''),
                "email": row.get('SecondaryContactEmail', ''),
                "phone": row.get('SecondaryContactPhone', ''),
                "fax": row.get('SecondaryContactFax', '')
            },
            "links": {
                "additional_info": row.get('AdditionalInfoLink', ''),
                "sam_gov": row.get('Link', '')
            },
            "description": row.get('Description', ''),
            "organization_type": row.get('OrganizationType', ''),
            "location": {
                "state": row.get('State', ''),
                "city": row.get('City', ''),
                "zip": row.get('ZipCode', ''),
                "country": row.get('CountryCode', '')
            }
        }
    
    async def get_naics_info(self, naics_code: str) -> Dict[str, Any]:
        """Get NAICS code information"""
        
        # NAICS codes database (sample - would be complete in production)
        naics_db = {
            "541511": {
                "code": "541511",
                "title": "Custom Computer Programming Services",
                "description": "This industry comprises establishments primarily engaged in writing, modifying, testing, and supporting software to meet the needs of a particular customer.",
                "size_standard": "$22.5 million",
                "sector": "Professional, Scientific, and Technical Services"
            },
            "541512": {
                "code": "541512", 
                "title": "Computer Systems Design Services",
                "description": "This industry comprises establishments primarily engaged in planning and designing computer systems that integrate computer hardware, software, and communication technologies.",
                "size_standard": "$22.5 million",
                "sector": "Professional, Scientific, and Technical Services"
            },
            "541513": {
                "code": "541513",
                "title": "Computer Facilities Management Services", 
                "description": "This industry comprises establishments primarily engaged in providing on-site management and operation of clients' computer systems and/or data processing facilities.",
                "size_standard": "$22.5 million",
                "sector": "Professional, Scientific, and Technical Services"
            },
            "541519": {
                "code": "541519",
                "title": "Other Computer Related Services",
                "description": "This industry comprises establishments primarily engaged in providing computer related services (except custom programming, systems design, facilities management, or training).",
                "size_standard": "$22.5 million", 
                "sector": "Professional, Scientific, and Technical Services"
            }
        }
        
        return naics_db.get(naics_code, {
            "error": f"NAICS code {naics_code} not found",
            "code": naics_code
        })
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()


class AgencyDirectory:
    """Government agency information and contacts"""
    
    def __init__(self):
        self.agencies = {
            "Department of Veterans Affairs": {
                "abbreviation": "VA",
                "type": "Department",
                "website": "https://www.va.gov/",
                "contracting_office": "VA Office of Acquisition, Logistics, and Construction",
                "small_business_office": "OSDBU",
                "common_naics": ["541511", "541512", "621111", "238210"],
                "typical_opportunities": [
                    "Healthcare IT systems",
                    "Medical equipment", 
                    "Construction services",
                    "Professional services"
                ]
            },
            "General Services Administration": {
                "abbreviation": "GSA",
                "type": "Independent Agency",
                "website": "https://www.gsa.gov/",
                "contracting_office": "Federal Acquisition Service",
                "small_business_office": "Office of Small and Disadvantaged Business Utilization",
                "common_naics": ["541511", "541512", "541519", "236220"],
                "typical_opportunities": [
                    "IT services and solutions",
                    "Building maintenance",
                    "Professional services",
                    "Supplies and equipment"
                ]
            },
            "Department of Defense": {
                "abbreviation": "DOD",
                "type": "Department", 
                "website": "https://www.defense.gov/",
                "contracting_office": "Defense Acquisition University",
                "small_business_office": "OSBP",
                "common_naics": ["541511", "541512", "336411", "541330"],
                "typical_opportunities": [
                    "Defense systems",
                    "Cybersecurity services",
                    "Research and development",
                    "Engineering services"
                ]
            }
        }
    
    def get_agency_info(self, agency_name: str) -> Dict[str, Any]:
        """Get information about a specific agency"""
        
        # Try exact match first
        if agency_name in self.agencies:
            return self.agencies[agency_name]
        
        # Try partial match
        for name, info in self.agencies.items():
            if agency_name.lower() in name.lower() or info["abbreviation"].lower() == agency_name.lower():
                return {**info, "matched_name": name}
        
        return {"error": f"Agency '{agency_name}' not found"}
    
    def list_agencies(self) -> List[str]:
        """List all available agencies"""
        return list(self.agencies.keys())


# Initialize the MCP server
server = Server("govbiz-sam-mcp")

# Initialize services
sam_service = SAMDataService()
agency_directory = AgencyDirectory()

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available SAM.gov resources"""
    
    resources = [
        Resource(
            uri="sam://naics-codes",
            name="NAICS Codes Database",
            description="Complete NAICS codes with size standards",
            mimeType="application/json"
        ),
        Resource(
            uri="sam://agencies",
            name="Government Agencies Directory",
            description="Federal agency information and contacts",
            mimeType="application/json"
        ),
        Resource(
            uri="sam://set-aside-codes",
            name="Set-Aside Codes",
            description="Small business set-aside type definitions",
            mimeType="application/json"
        ),
        Resource(
            uri="sam://opportunity-types",
            name="Opportunity Types",
            description="Contract opportunity type definitions",
            mimeType="application/json"
        ),
        Resource(
            uri="sam://csv-schema",
            name="CSV Data Schema",
            description="SAM.gov CSV file structure and field definitions",
            mimeType="application/json"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read SAM.gov resource content"""
    
    if uri == "sam://naics-codes":
        # This would be a complete NAICS database in production
        naics_codes = {
            "541511": {
                "title": "Custom Computer Programming Services",
                "size_standard": "$22.5 million",
                "sector": "Professional, Scientific, and Technical Services"
            },
            "541512": {
                "title": "Computer Systems Design Services", 
                "size_standard": "$22.5 million",
                "sector": "Professional, Scientific, and Technical Services"
            },
            "541513": {
                "title": "Computer Facilities Management Services",
                "size_standard": "$22.5 million",
                "sector": "Professional, Scientific, and Technical Services"
            }
        }
        return json.dumps(naics_codes, indent=2)
    
    elif uri == "sam://agencies":
        return json.dumps(agency_directory.agencies, indent=2)
    
    elif uri == "sam://set-aside-codes":
        set_aside_codes = {
            "SBA": "Small Business Set-Aside",
            "8A": "8(a) Program",
            "WOSB": "Women-Owned Small Business",
            "SDVOSB": "Service-Disabled Veteran-Owned Small Business",
            "HUBZ": "HUBZone Small Business",
            "NONE": "Full and Open Competition"
        }
        return json.dumps(set_aside_codes, indent=2)
    
    elif uri == "sam://opportunity-types":
        opportunity_types = {
            "Sources Sought": "Market research to identify potential sources",
            "Request for Information": "Seeking information about capabilities",
            "Solicitation": "Formal request for proposals or quotes",
            "Award Notice": "Notification of contract award",
            "Intent to Bundle": "Notice of intent to bundle requirements",
            "Special Notice": "Special announcements and notices"
        }
        return json.dumps(opportunity_types, indent=2)
    
    elif uri == "sam://csv-schema":
        schema = {
            "description": "SAM.gov Contract Opportunities CSV Schema",
            "total_columns": 44,
            "columns": sam_service.csv_columns,
            "key_fields": {
                "unique_identifier": "NoticeId",
                "title": "Title", 
                "agency": "Department/Ind.Agency",
                "posted_date": "PostedDate",
                "response_deadline": "ResponseDeadLine",
                "active_status": "Active",
                "opportunity_type": "Type",
                "naics_code": "NaicsCode",
                "set_aside": "SetAside"
            },
            "date_formats": {
                "PostedDate": "MM/DD/YYYY",
                "ArchiveDate": "MM/DD/YYYY", 
                "ResponseDeadLine": "MM/DD/YYYY HH:MM:SS AM/PM",
                "AwardDate": "MM/DD/YYYY"
            }
        }
        return json.dumps(schema, indent=2)
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available SAM.gov tools"""
    
    tools = [
        Tool(
            name="download_csv",
            description="Download SAM.gov opportunities CSV file",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_size_mb": {"type": "integer", "description": "Maximum file size in MB", "default": 500},
                    "return_content": {"type": "boolean", "description": "Return CSV content in response", "default": False}
                }
            }
        ),
        Tool(
            name="parse_csv_sample",
            description="Parse and analyze a sample of CSV data",
            inputSchema={
                "type": "object", 
                "properties": {
                    "csv_content": {"type": "string", "description": "CSV content to parse"},
                    "sample_size": {"type": "integer", "description": "Number of sample rows", "default": 10}
                },
                "required": ["csv_content"]
            }
        ),
        Tool(
            name="search_opportunities",
            description="Search opportunities in CSV data with filters",
            inputSchema={
                "type": "object",
                "properties": {
                    "csv_content": {"type": "string", "description": "CSV content to search"},
                    "filters": {
                        "type": "object",
                        "description": "Search filters",
                        "properties": {
                            "keywords": {"type": "array", "items": {"type": "string"}},
                            "naics_codes": {"type": "array", "items": {"type": "string"}},
                            "agencies": {"type": "array", "items": {"type": "string"}},
                            "set_asides": {"type": "array", "items": {"type": "string"}},
                            "notice_type": {"type": "string"},
                            "active_only": {"type": "boolean", "default": True},
                            "posted_after": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                            "limit": {"type": "integer", "default": 100}
                        }
                    }
                },
                "required": ["csv_content"]
            }
        ),
        Tool(
            name="get_opportunity_details",
            description="Get detailed information about a specific opportunity",
            inputSchema={
                "type": "object",
                "properties": {
                    "notice_id": {"type": "string", "description": "Notice ID to look up"},
                    "csv_content": {"type": "string", "description": "CSV content to search in"}
                },
                "required": ["notice_id", "csv_content"]
            }
        ),
        Tool(
            name="validate_naics",
            description="Validate and get information about NAICS codes",
            inputSchema={
                "type": "object",
                "properties": {
                    "naics_code": {"type": "string", "description": "NAICS code to validate"},
                    "business_size": {"type": "string", "description": "Business annual revenue for size check"}
                },
                "required": ["naics_code"]
            }
        ),
        Tool(
            name="get_agency_info",
            description="Get information about a government agency",
            inputSchema={
                "type": "object",
                "properties": {
                    "agency_name": {"type": "string", "description": "Agency name or abbreviation"}
                },
                "required": ["agency_name"]
            }
        ),
        Tool(
            name="track_amendments",
            description="Track changes to opportunities (mock implementation)",
            inputSchema={
                "type": "object",
                "properties": {
                    "notice_ids": {"type": "array", "items": {"type": "string"}, "description": "Notice IDs to track"},
                    "check_interval_hours": {"type": "integer", "description": "Check interval in hours", "default": 24}
                },
                "required": ["notice_ids"]
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "download_csv":
        result = await sam_service.download_csv(
            max_size_mb=arguments.get("max_size_mb", 500)
        )
        
        # Don't return content by default due to size
        if not arguments.get("return_content", False) and "csv_content" in result:
            content_size = len(result["csv_content"])
            del result["csv_content"]
            result["content_available"] = True
            result["content_size_chars"] = content_size
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "parse_csv_sample":
        result = await sam_service.parse_csv_sample(
            csv_content=arguments["csv_content"],
            sample_size=arguments.get("sample_size", 10)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "search_opportunities":
        opportunities = await sam_service.search_opportunities(
            csv_content=arguments["csv_content"],
            filters=arguments.get("filters", {})
        )
        
        result = {
            "total_results": len(opportunities),
            "filters_applied": arguments.get("filters", {}),
            "opportunities": opportunities
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_opportunity_details":
        # Search for specific opportunity
        opportunities = await sam_service.search_opportunities(
            csv_content=arguments["csv_content"],
            filters={"notice_ids": [arguments["notice_id"]], "limit": 1}
        )
        
        if opportunities:
            result = opportunities[0]
        else:
            result = {"error": f"Opportunity {arguments['notice_id']} not found"}
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "validate_naics":
        naics_info = await sam_service.get_naics_info(arguments["naics_code"])
        
        # Add size standard validation if business size provided
        if "business_size" in arguments and "size_standard" in naics_info:
            try:
                business_revenue = float(arguments["business_size"].replace("$", "").replace("M", "").replace("million", ""))
                size_limit = float(naics_info["size_standard"].replace("$", "").replace(" million", ""))
                
                naics_info["size_qualification"] = {
                    "qualifies_as_small": business_revenue <= size_limit,
                    "business_size": f"${business_revenue}M",
                    "size_standard": naics_info["size_standard"]
                }
            except:
                naics_info["size_qualification"] = {"error": "Could not parse business size"}
        
        return [types.TextContent(type="text", text=json.dumps(naics_info, indent=2))]
    
    elif name == "get_agency_info":
        agency_info = agency_directory.get_agency_info(arguments["agency_name"])
        return [types.TextContent(type="text", text=json.dumps(agency_info, indent=2))]
    
    elif name == "track_amendments":
        # Mock implementation for tracking opportunity changes
        result = {
            "tracking_started": True,
            "notice_ids": arguments["notice_ids"],
            "check_interval_hours": arguments.get("check_interval_hours", 24),
            "next_check": (datetime.now() + timedelta(hours=arguments.get("check_interval_hours", 24))).isoformat(),
            "note": "This is a mock implementation. In production, this would set up automated monitoring."
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Run the MCP server"""
    
    from mcp.server.stdio import stdio_server
    
    try:
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
    finally:
        await sam_service.close()

if __name__ == "__main__":
    asyncio.run(main())