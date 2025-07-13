"""
Smoke tests for the Sources Sought AI Web Application
"""

import asyncio
import json
import requests
import subprocess
import time
from typing import Dict, Any
import os

from smoke_test_framework import smoke_test

class WebAppTester:
    """Helper class for testing web application"""
    
    def __init__(self):
        self.base_url = os.getenv('WEB_BASE_URL', 'http://localhost:3000')
        self.build_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'web')
        
    def check_url_response(self, url: str, timeout: int = 10) -> Dict[str, Any]:
        """Check if URL responds successfully"""
        try:
            start_time = time.time()
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            response_time = (time.time() - start_time) * 1000
            
            return {
                'success': 200 <= response.status_code < 400,
                'status_code': response.status_code,
                'response_time_ms': response_time,
                'content_length': len(response.content),
                'content_type': response.headers.get('content-type', ''),
                'error': None if 200 <= response.status_code < 400 else f'HTTP {response.status_code}'
            }
            
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': f'Request to {url} timed out after {timeout} seconds'
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': f'Could not connect to {url}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Request error: {e}'
            }
    
    def check_build_artifacts(self) -> Dict[str, Any]:
        """Check if build artifacts exist"""
        build_artifacts = [
            '.next',
            'package.json',
            'next.config.js',
            'tailwind.config.ts',
            'tsconfig.json'
        ]
        
        missing_artifacts = []
        existing_artifacts = []
        
        for artifact in build_artifacts:
            artifact_path = os.path.join(self.build_dir, artifact)
            if os.path.exists(artifact_path):
                existing_artifacts.append(artifact)
            else:
                missing_artifacts.append(artifact)
        
        return {
            'success': len(missing_artifacts) == 0,
            'existing_artifacts': existing_artifacts,
            'missing_artifacts': missing_artifacts,
            'build_dir': self.build_dir,
            'error': f'Missing artifacts: {missing_artifacts}' if missing_artifacts else None
        }
    
    def check_package_dependencies(self) -> Dict[str, Any]:
        """Check if package.json dependencies are installed"""
        try:
            package_json_path = os.path.join(self.build_dir, 'package.json')
            node_modules_path = os.path.join(self.build_dir, 'node_modules')
            
            if not os.path.exists(package_json_path):
                return {
                    'success': False,
                    'error': 'package.json not found'
                }
            
            # Check if node_modules exists
            node_modules_exists = os.path.exists(node_modules_path)
            
            # Read package.json to get dependency count
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)
            
            dependencies = package_data.get('dependencies', {})
            dev_dependencies = package_data.get('devDependencies', {})
            total_deps = len(dependencies) + len(dev_dependencies)
            
            return {
                'success': node_modules_exists,
                'node_modules_exists': node_modules_exists,
                'total_dependencies': total_deps,
                'production_dependencies': len(dependencies),
                'dev_dependencies': len(dev_dependencies),
                'error': 'node_modules directory not found - run npm install' if not node_modules_exists else None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error checking dependencies: {e}'
            }

# Initialize web app tester
web_tester = WebAppTester()

@smoke_test("web-app", "server_connectivity", timeout=15)
def test_server_connectivity():
    """Test basic connectivity to web application server"""
    return web_tester.check_url_response(web_tester.base_url)

@smoke_test("web-app", "home_page", timeout=15)
def test_home_page():
    """Test home page loads successfully"""
    result = web_tester.check_url_response(web_tester.base_url)
    
    if result['success']:
        # Additional checks for home page
        content_type = result.get('content_type', '')
        if 'text/html' in content_type:
            result['is_html'] = True
        else:
            result['success'] = False
            result['error'] = f'Expected HTML content, got {content_type}'
    
    return result

@smoke_test("web-app", "login_page", timeout=15)
def test_login_page():
    """Test login page accessibility"""
    login_url = f"{web_tester.base_url}/login"
    return web_tester.check_url_response(login_url)

@smoke_test("web-app", "dashboard_page", timeout=15)
def test_dashboard_page():
    """Test dashboard page (may redirect to login)"""
    dashboard_url = f"{web_tester.base_url}/dashboard"
    result = web_tester.check_url_response(dashboard_url)
    
    # Dashboard may redirect to login - both are acceptable for smoke test
    if result['status_code'] in [200, 302, 401]:
        result['success'] = True
        result['accessible'] = True
    
    return result

@smoke_test("web-app", "api_routes", timeout=20)
def test_api_routes():
    """Test Next.js API routes"""
    api_routes = [
        '/api/health',
        '/api/auth/session'
    ]
    
    results = {}
    successful_routes = 0
    
    for route in api_routes:
        url = f"{web_tester.base_url}{route}"
        result = web_tester.check_url_response(url)
        results[route] = result
        
        # API routes may return different status codes but should respond
        if result.get('status_code') and result['status_code'] != 0:
            successful_routes += 1
    
    return {
        'success': successful_routes > 0,
        'routes_tested': len(api_routes),
        'responding_routes': successful_routes,
        'detailed_results': results,
        'error': 'No API routes responding' if successful_routes == 0 else None
    }

@smoke_test("web-app", "static_assets", timeout=20)
def test_static_assets():
    """Test static asset loading"""
    # Test common static asset paths
    asset_paths = [
        '/favicon.ico',
        '/_next/static/css',  # Next.js CSS
        '/_next/static/js'    # Next.js JS
    ]
    
    results = {}
    successful_assets = 0
    
    for path in asset_paths:
        url = f"{web_tester.base_url}{path}"
        result = web_tester.check_url_response(url)
        results[path] = result
        
        # Static assets should return 200 or 404 (if path structure differs)
        if result.get('status_code') in [200, 404]:
            successful_assets += 1
    
    return {
        'success': successful_assets > 0,
        'assets_tested': len(asset_paths),
        'responding_assets': successful_assets,
        'detailed_results': results,
        'error': 'No static assets found' if successful_assets == 0 else None
    }

@smoke_test("web-app", "build_artifacts", timeout=10)
def test_build_artifacts():
    """Test web application build artifacts exist"""
    return web_tester.check_build_artifacts()

@smoke_test("web-app", "package_dependencies", timeout=10)
def test_package_dependencies():
    """Test package dependencies are installed"""
    return web_tester.check_package_dependencies()

@smoke_test("web-app", "next_config", timeout=10)
def test_next_config():
    """Test Next.js configuration"""
    try:
        config_path = os.path.join(web_tester.build_dir, 'next.config.js')
        
        if not os.path.exists(config_path):
            return {
                'success': False,
                'error': 'next.config.js not found'
            }
        
        # Check if config file is readable
        with open(config_path, 'r') as f:
            config_content = f.read()
        
        return {
            'success': True,
            'config_exists': True,
            'config_size': len(config_content),
            'has_content': len(config_content.strip()) > 0
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Error reading Next.js config: {e}'
        }

@smoke_test("web-app", "tailwind_config", timeout=10)
def test_tailwind_config():
    """Test Tailwind CSS configuration"""
    try:
        config_path = os.path.join(web_tester.build_dir, 'tailwind.config.ts')
        
        if not os.path.exists(config_path):
            # Try .js extension as fallback
            config_path = os.path.join(web_tester.build_dir, 'tailwind.config.js')
        
        if not os.path.exists(config_path):
            return {
                'success': False,
                'error': 'tailwind.config.ts/js not found'
            }
        
        # Check if config file is readable
        with open(config_path, 'r') as f:
            config_content = f.read()
        
        return {
            'success': True,
            'config_exists': True,
            'config_file': os.path.basename(config_path),
            'config_size': len(config_content),
            'has_content': len(config_content.strip()) > 0
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Error reading Tailwind config: {e}'
        }

@smoke_test("web-app", "typescript_config", timeout=10)
def test_typescript_config():
    """Test TypeScript configuration"""
    try:
        config_path = os.path.join(web_tester.build_dir, 'tsconfig.json')
        
        if not os.path.exists(config_path):
            return {
                'success': False,
                'error': 'tsconfig.json not found'
            }
        
        # Check if config file is valid JSON
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        return {
            'success': True,
            'config_exists': True,
            'has_compiler_options': 'compilerOptions' in config_data,
            'has_include': 'include' in config_data,
            'config_keys': list(config_data.keys())
        }
        
    except json.JSONDecodeError:
        return {
            'success': False,
            'error': 'tsconfig.json is not valid JSON'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Error reading TypeScript config: {e}'
        }

@smoke_test("web-app", "environment_variables", timeout=10)
def test_environment_variables():
    """Test environment variables configuration"""
    try:
        env_files = ['.env.local', '.env', '.env.example']
        found_env_files = []
        
        for env_file in env_files:
            env_path = os.path.join(web_tester.build_dir, env_file)
            if os.path.exists(env_path):
                found_env_files.append(env_file)
        
        # Check for critical environment variables
        critical_vars = [
            'NEXTAUTH_URL',
            'NEXTAUTH_SECRET',
            'GOOGLE_CLIENT_ID',
            'API_BASE_URL'
        ]
        
        configured_vars = []
        for var in critical_vars:
            if os.getenv(var):
                configured_vars.append(var)
        
        return {
            'success': len(found_env_files) > 0,
            'env_files_found': found_env_files,
            'critical_vars_configured': configured_vars,
            'env_setup_complete': len(configured_vars) >= 2,  # At least some vars configured
            'error': 'No environment files found' if len(found_env_files) == 0 else None
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Error checking environment variables: {e}'
        }