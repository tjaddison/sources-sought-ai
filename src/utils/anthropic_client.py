"""
Anthropic client wrapper for Claude API interactions.
Provides standardized interface for all AI operations in the system.
"""

import asyncio
from typing import Dict, Any, List, Optional, Union
import anthropic
from anthropic import AsyncAnthropic

from ..core.config import config, initialize_config
from ..utils.logger import get_logger

logger = get_logger("anthropic_client")


class AnthropicClient:
    """Wrapper for Anthropic Claude API with configuration management"""
    
    def __init__(self):
        self.client: Optional[AsyncAnthropic] = None
        self.initialized = False
        
    async def initialize(self):
        """Initialize the Anthropic client with API key from config"""
        if self.initialized:
            return
        
        # Ensure config is loaded
        await initialize_config()
        
        if not config.ai.anthropic_api_key:
            raise ValueError("Anthropic API key not found in configuration")
        
        self.client = AsyncAnthropic(api_key=config.ai.anthropic_api_key)
        self.initialized = True
        logger.info("Anthropic client initialized successfully")
    
    async def create_message(self, 
                           messages: List[Dict[str, str]], 
                           model: Optional[str] = None,
                           max_tokens: Optional[int] = None,
                           temperature: Optional[float] = None,
                           system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Create a message using Claude API"""
        
        if not self.initialized:
            await self.initialize()
        
        # Use configuration defaults if not specified
        model = model or config.ai.default_model
        max_tokens = max_tokens or config.ai.max_tokens
        temperature = temperature or config.ai.temperature
        
        try:
            # Prepare the request
            request_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages
            }
            
            if system_prompt:
                request_params["system"] = system_prompt
            
            logger.debug(f"Sending request to Claude {model}")
            
            # Make the API call
            response = await self.client.messages.create(**request_params)
            
            # Extract the response content
            result = {
                "content": response.content[0].text if response.content else "",
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                },
                "stop_reason": response.stop_reason
            }
            
            logger.debug(f"Claude response: {result['usage']['total_tokens']} tokens")
            return result
            
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Claude: {e}")
            raise
    
    async def analyze_text(self, 
                          text: str, 
                          analysis_prompt: str,
                          model: Optional[str] = None) -> str:
        """Analyze text using Claude with a specific analysis prompt"""
        
        model = model or config.ai.analysis_model
        
        messages = [
            {
                "role": "user",
                "content": f"{analysis_prompt}\n\nText to analyze:\n{text}"
            }
        ]
        
        response = await self.create_message(messages, model=model)
        return response["content"]
    
    async def generate_content(self, 
                             prompt: str, 
                             context: Optional[str] = None,
                             model: Optional[str] = None) -> str:
        """Generate content using Claude"""
        
        model = model or config.ai.generation_model
        
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nTask:\n{prompt}"
        
        messages = [
            {
                "role": "user",
                "content": full_prompt
            }
        ]
        
        response = await self.create_message(messages, model=model)
        return response["content"]
    
    async def extract_structured_data(self, 
                                    text: str, 
                                    schema_description: str,
                                    model: Optional[str] = None) -> str:
        """Extract structured data from text using Claude"""
        
        model = model or config.ai.analysis_model
        
        system_prompt = f"""You are a data extraction specialist. Extract information from the provided text according to this schema:

{schema_description}

Return only the extracted data in the requested format. Be precise and accurate."""
        
        messages = [
            {
                "role": "user",
                "content": text
            }
        ]
        
        response = await self.create_message(
            messages, 
            model=model, 
            system_prompt=system_prompt
        )
        return response["content"]
    
    async def quick_analysis(self, 
                           text: str, 
                           question: str) -> str:
        """Quick analysis using the fast Haiku model"""
        
        model = config.ai.quick_model
        
        messages = [
            {
                "role": "user",
                "content": f"Question: {question}\n\nText: {text}\n\nProvide a concise answer:"
            }
        ]
        
        response = await self.create_message(
            messages, 
            model=model, 
            max_tokens=1000,
            temperature=0.3
        )
        return response["content"]
    
    async def classification(self, 
                           text: str, 
                           categories: List[str],
                           model: Optional[str] = None) -> str:
        """Classify text into one of the provided categories"""
        
        model = model or config.ai.quick_model
        
        categories_text = "\n".join([f"- {cat}" for cat in categories])
        
        system_prompt = f"""You are a text classifier. Classify the provided text into exactly one of these categories:

{categories_text}

Respond with only the category name, nothing else."""
        
        messages = [
            {
                "role": "user",
                "content": text
            }
        ]
        
        response = await self.create_message(
            messages, 
            model=model, 
            system_prompt=system_prompt,
            max_tokens=50,
            temperature=0.1
        )
        return response["content"].strip()
    
    async def summarize(self, 
                       text: str, 
                       max_length: int = 500,
                       model: Optional[str] = None) -> str:
        """Summarize text to a specified maximum length"""
        
        model = model or config.ai.quick_model
        
        system_prompt = f"""Summarize the provided text in approximately {max_length} characters or less. 
Focus on the most important information and key points. Be concise and clear."""
        
        messages = [
            {
                "role": "user",
                "content": text
            }
        ]
        
        response = await self.create_message(
            messages, 
            model=model, 
            system_prompt=system_prompt,
            max_tokens=max_length // 3,  # Rough estimate for token to character ratio
            temperature=0.3
        )
        return response["content"]
    
    async def check_compliance(self, 
                             text: str, 
                             requirements: List[str],
                             model: Optional[str] = None) -> Dict[str, Any]:
        """Check if text complies with specified requirements"""
        
        model = model or config.ai.analysis_model
        
        requirements_text = "\n".join([f"{i+1}. {req}" for i, req in enumerate(requirements)])
        
        system_prompt = f"""You are a compliance checker. Evaluate the provided text against these requirements:

{requirements_text}

For each requirement, determine if it is MET or NOT MET and provide a brief explanation.
Return your response in this JSON format:
{{
    "overall_compliance": true/false,
    "compliance_score": 0-100,
    "requirements": [
        {{
            "requirement": "requirement text",
            "status": "MET" or "NOT MET",
            "explanation": "brief explanation"
        }}
    ],
    "recommendations": ["list of recommendations for improvement"]
}}"""
        
        messages = [
            {
                "role": "user",
                "content": text
            }
        ]
        
        response = await self.create_message(
            messages, 
            model=model, 
            system_prompt=system_prompt,
            temperature=0.2
        )
        
        try:
            import json
            return json.loads(response["content"])
        except json.JSONDecodeError:
            logger.warning("Failed to parse compliance response as JSON")
            return {
                "overall_compliance": False,
                "compliance_score": 0,
                "requirements": [],
                "recommendations": ["Failed to parse compliance check response"],
                "raw_response": response["content"]
            }


# Global client instance
anthropic_client = AnthropicClient()


# Convenience functions for easy access
async def analyze_text(text: str, analysis_prompt: str, model: Optional[str] = None) -> str:
    """Analyze text using Claude"""
    return await anthropic_client.analyze_text(text, analysis_prompt, model)


async def generate_content(prompt: str, context: Optional[str] = None, model: Optional[str] = None) -> str:
    """Generate content using Claude"""
    return await anthropic_client.generate_content(prompt, context, model)


async def extract_structured_data(text: str, schema_description: str, model: Optional[str] = None) -> str:
    """Extract structured data from text"""
    return await anthropic_client.extract_structured_data(text, schema_description, model)


async def quick_analysis(text: str, question: str) -> str:
    """Quick analysis using Haiku model"""
    return await anthropic_client.quick_analysis(text, question)


async def classification(text: str, categories: List[str], model: Optional[str] = None) -> str:
    """Classify text into categories"""
    return await anthropic_client.classification(text, categories, model)


async def summarize(text: str, max_length: int = 500, model: Optional[str] = None) -> str:
    """Summarize text"""
    return await anthropic_client.summarize(text, max_length, model)


async def check_compliance(text: str, requirements: List[str], model: Optional[str] = None) -> Dict[str, Any]:
    """Check text compliance against requirements"""
    return await anthropic_client.check_compliance(text, requirements, model)