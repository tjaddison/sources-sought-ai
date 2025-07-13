"""
Smoke tests for all MCP servers in the Sources Sought AI system
"""

import asyncio
import json
import subprocess
import time
import requests
import docker
from typing import Dict, Any
import os
import sys

from smoke_test_framework import smoke_test

class MCPServerTester:
    """Helper class for testing MCP servers"""
    
    def __init__(self):
        self.docker_client = None
        self.mcp_servers = [
            "sources-sought-email-mcp",
            "sources-sought-sam-mcp", 
            "sources-sought-docgen-mcp",
            "sources-sought-search-mcp",
            "sources-sought-slack-mcp",
            "sources-sought-database-mcp",
            "sources-sought-aws-mcp",
            "sources-sought-crm-mcp",
            "sources-sought-monitoring-mcp",
            "sources-sought-prompts-mcp"
        ]
        
    def get_docker_client(self):
        """Get Docker client, initialize if needed"""
        if self.docker_client is None:
            try:
                self.docker_client = docker.from_env()
            except Exception as e:
                raise Exception(f"Failed to connect to Docker: {e}")
        return self.docker_client
    
    def check_container_running(self, container_name: str) -> Dict[str, Any]:
        """Check if a Docker container is running"""
        try:
            client = self.get_docker_client()
            container = client.containers.get(container_name)
            
            if container.status == 'running':
                # Get container stats
                stats = container.stats(stream=False)
                memory_usage = stats['memory_stats'].get('usage', 0)
                memory_limit = stats['memory_stats'].get('limit', 0)
                memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
                
                return {
                    'success': True,
                    'status': container.status,
                    'memory_usage_mb': memory_usage / 1024 / 1024,
                    'memory_percent': memory_percent,
                    'container_id': container.short_id
                }
            else:
                return {
                    'success': False,
                    'error': f"Container {container_name} is not running (status: {container.status})"
                }
        except docker.errors.NotFound:
            return {
                'success': False,
                'error': f"Container {container_name} not found"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Error checking container {container_name}: {e}"
            }
    
    def check_mcp_health(self, server_name: str, port: int) -> Dict[str, Any]:
        """Check MCP server health endpoint"""
        try:
            url = f"http://localhost:{port}/health"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                health_data = response.json()
                return {
                    'success': True,
                    'status_code': response.status_code,
                    'response_time_ms': response.elapsed.total_seconds() * 1000,
                    'health_data': health_data
                }
            else:
                return {
                    'success': False,
                    'error': f"Health check failed with status {response.status_code}",
                    'response_text': response.text[:200]
                }
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': f"Health check timed out for {server_name}"
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': f"Could not connect to {server_name} on port {port}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Health check error for {server_name}: {e}"
            }

# Initialize tester
mcp_tester = MCPServerTester()

# Port mappings for MCP servers (based on docker-compose.yml)
MCP_PORTS = {
    "sources-sought-email-mcp": 8001,
    "sources-sought-sam-mcp": 8002,
    "sources-sought-docgen-mcp": 8003,
    "sources-sought-search-mcp": 8004,
    "sources-sought-slack-mcp": 8005,
    "sources-sought-database-mcp": 8006,
    "sources-sought-aws-mcp": 8007,
    "sources-sought-crm-mcp": 8008,
    "sources-sought-monitoring-mcp": 8009,
    "sources-sought-prompts-mcp": 8010
}

@smoke_test("mcp-servers", "docker_connectivity", timeout=10)
def test_docker_connectivity():
    """Test Docker daemon connectivity"""
    try:
        client = mcp_tester.get_docker_client()
        client.ping()
        return {
            'success': True,
            'docker_version': client.version()['Version']
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Docker connectivity failed: {e}"
        }

@smoke_test("mcp-servers", "email_mcp_container", timeout=15)
def test_email_mcp_container():
    """Test Email MCP server container"""
    return mcp_tester.check_container_running("sources-sought-email-mcp")

@smoke_test("mcp-servers", "email_mcp_health", timeout=10)
def test_email_mcp_health():
    """Test Email MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-email-mcp", MCP_PORTS["sources-sought-email-mcp"])

@smoke_test("mcp-servers", "sam_mcp_container", timeout=15)
def test_sam_mcp_container():
    """Test SAM MCP server container"""
    return mcp_tester.check_container_running("sources-sought-sam-mcp")

@smoke_test("mcp-servers", "sam_mcp_health", timeout=10)
def test_sam_mcp_health():
    """Test SAM MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-sam-mcp", MCP_PORTS["sources-sought-sam-mcp"])

@smoke_test("mcp-servers", "docgen_mcp_container", timeout=15)
def test_docgen_mcp_container():
    """Test Document Generation MCP server container"""
    return mcp_tester.check_container_running("sources-sought-docgen-mcp")

@smoke_test("mcp-servers", "docgen_mcp_health", timeout=10)
def test_docgen_mcp_health():
    """Test Document Generation MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-docgen-mcp", MCP_PORTS["sources-sought-docgen-mcp"])

@smoke_test("mcp-servers", "search_mcp_container", timeout=15)
def test_search_mcp_container():
    """Test Search MCP server container"""
    return mcp_tester.check_container_running("sources-sought-search-mcp")

@smoke_test("mcp-servers", "search_mcp_health", timeout=10)
def test_search_mcp_health():
    """Test Search MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-search-mcp", MCP_PORTS["sources-sought-search-mcp"])

@smoke_test("mcp-servers", "slack_mcp_container", timeout=15)
def test_slack_mcp_container():
    """Test Slack MCP server container"""
    return mcp_tester.check_container_running("sources-sought-slack-mcp")

@smoke_test("mcp-servers", "slack_mcp_health", timeout=10)
def test_slack_mcp_health():
    """Test Slack MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-slack-mcp", MCP_PORTS["sources-sought-slack-mcp"])

@smoke_test("mcp-servers", "database_mcp_container", timeout=15)
def test_database_mcp_container():
    """Test Database MCP server container"""
    return mcp_tester.check_container_running("sources-sought-database-mcp")

@smoke_test("mcp-servers", "database_mcp_health", timeout=10)
def test_database_mcp_health():
    """Test Database MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-database-mcp", MCP_PORTS["sources-sought-database-mcp"])

@smoke_test("mcp-servers", "aws_mcp_container", timeout=15)
def test_aws_mcp_container():
    """Test AWS MCP server container"""
    return mcp_tester.check_container_running("sources-sought-aws-mcp")

@smoke_test("mcp-servers", "aws_mcp_health", timeout=10)
def test_aws_mcp_health():
    """Test AWS MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-aws-mcp", MCP_PORTS["sources-sought-aws-mcp"])

@smoke_test("mcp-servers", "crm_mcp_container", timeout=15)
def test_crm_mcp_container():
    """Test CRM MCP server container"""
    return mcp_tester.check_container_running("sources-sought-crm-mcp")

@smoke_test("mcp-servers", "crm_mcp_health", timeout=10)
def test_crm_mcp_health():
    """Test CRM MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-crm-mcp", MCP_PORTS["sources-sought-crm-mcp"])

@smoke_test("mcp-servers", "monitoring_mcp_container", timeout=15)
def test_monitoring_mcp_container():
    """Test Monitoring MCP server container"""
    return mcp_tester.check_container_running("sources-sought-monitoring-mcp")

@smoke_test("mcp-servers", "monitoring_mcp_health", timeout=10)
def test_monitoring_mcp_health():
    """Test Monitoring MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-monitoring-mcp", MCP_PORTS["sources-sought-monitoring-mcp"])

@smoke_test("mcp-servers", "prompts_mcp_container", timeout=15)
def test_prompts_mcp_container():
    """Test Prompts MCP server container"""
    return mcp_tester.check_container_running("sources-sought-prompts-mcp")

@smoke_test("mcp-servers", "prompts_mcp_health", timeout=10)
def test_prompts_mcp_health():
    """Test Prompts MCP server health endpoint"""
    return mcp_tester.check_mcp_health("sources-sought-prompts-mcp", MCP_PORTS["sources-sought-prompts-mcp"])

@smoke_test("mcp-servers", "all_mcp_containers_running", timeout=30)
def test_all_mcp_containers_running():
    """Test that all MCP server containers are running"""
    results = {}
    all_running = True
    
    for server_name in mcp_tester.mcp_servers:
        result = mcp_tester.check_container_running(server_name)
        results[server_name] = result
        if not result['success']:
            all_running = False
    
    return {
        'success': all_running,
        'containers_checked': len(mcp_tester.mcp_servers),
        'containers_running': len([r for r in results.values() if r['success']]),
        'detailed_results': results,
        'error': None if all_running else "One or more MCP containers are not running"
    }

@smoke_test("mcp-servers", "mcp_servers_communication", timeout=45)
def test_mcp_servers_communication():
    """Test basic communication with all MCP servers"""
    results = {}
    all_healthy = True
    total_response_time = 0
    
    for server_name, port in MCP_PORTS.items():
        result = mcp_tester.check_mcp_health(server_name, port)
        results[server_name] = result
        
        if result['success']:
            total_response_time += result.get('response_time_ms', 0)
        else:
            all_healthy = False
    
    avg_response_time = total_response_time / len(MCP_PORTS) if MCP_PORTS else 0
    
    return {
        'success': all_healthy,
        'servers_checked': len(MCP_PORTS),
        'servers_healthy': len([r for r in results.values() if r['success']]),
        'average_response_time_ms': avg_response_time,
        'detailed_results': results,
        'error': None if all_healthy else "One or more MCP servers failed health check"
    }

@smoke_test("mcp-servers", "docker_compose_status", timeout=20)
def test_docker_compose_status():
    """Test overall Docker Compose stack status"""
    try:
        # Check if docker-compose.yml exists
        compose_file = os.path.join(os.path.dirname(__file__), '..', '..', 'docker-compose.yml')
        if not os.path.exists(compose_file):
            return {
                'success': False,
                'error': 'docker-compose.yml not found'
            }
        
        # Run docker-compose ps to get status
        result = subprocess.run(
            ['docker-compose', 'ps', '--format', 'json'],
            cwd=os.path.dirname(compose_file),
            capture_output=True,
            text=True,
            timeout=15
        )
        
        if result.returncode == 0:
            # Parse the output (each line is a JSON object)
            services = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        services.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            
            running_services = [s for s in services if s.get('State') == 'running']
            
            return {
                'success': len(running_services) > 0,
                'total_services': len(services),
                'running_services': len(running_services),
                'services_details': services,
                'error': None if len(running_services) > 0 else "No services are running"
            }
        else:
            return {
                'success': False,
                'error': f"docker-compose ps failed: {result.stderr}"
            }
            
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': "docker-compose ps command timed out"
        }
    except FileNotFoundError:
        return {
            'success': False,
            'error': "docker-compose command not found. Please install Docker Compose."
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error checking docker-compose status: {e}"
        }