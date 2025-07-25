import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config.settings import settings

logger = logging.getLogger(__name__)

@dataclass
class DealContext:
    """Container for deal context information"""
    deal_id: str
    activities: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    similar_deals: List[Dict[str, Any]] = None

class LLMContextBuilder:
    """
    LLM-powered context builder that generates intelligent historical context
    using similar deals and a dedicated LLM prompt
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize LLM context builder
        
        Args:
            llm_client: LLM client for context generation (optional, will use from sentiment analyzer if not provided)
        """
        self.llm_client = llm_client
        self.prompt_template = self._load_context_prompt()
        
        logger.info("LLM Context Builder initialized")
    
    def _load_context_prompt(self) -> str:
        """Load context analysis prompt from file"""
        prompt_path = Path("prompts/sales_context_analysis_prompt.txt")
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                template = f.read()
            logger.info(f"Loaded context analysis prompt from {prompt_path}")
            return template
        except FileNotFoundError:
            logger.error(f"Context analysis prompt file not found: {prompt_path}")
            return self._get_fallback_prompt()
        except Exception as e:
            logger.error(f"Error loading context analysis prompt: {e}")
            return self._get_fallback_prompt()
    
    def _get_fallback_prompt(self) -> str:
        """Fallback prompt if file loading fails"""
        return """
You are a sales analytics expert. Analyze these similar deals and provide historical context:

{similar_deals_data}

Generate analysis in this structure:
## SIMILAR DEALS CONTEXT
## SENTIMENT PATTERNS ANALYSIS
## LANGUAGE TONE ANALYSIS
## DEAL PROGRESSION PATTERNS
## CLIENT BEHAVIOR PATTERNS

Keep each section concise and actionable.
"""
    
    def build_context(
        self,
        deal_id: str,
        activities: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        similar_deals: List[Dict[str, Any]] = None,
        llm_client=None
    ) -> str:
        """
        Build comprehensive context using LLM analysis
        
        Args:
            deal_id: Current deal identifier
            activities: Deal activities (not used in LLM approach, kept for compatibility)
            metadata: Deal metadata (not used in LLM approach, kept for compatibility)
            similar_deals: Similar deals from RAG retrieval
            llm_client: Optional LLM client override
            
        Returns:
            Formatted context string generated by LLM
        """
        
        if not similar_deals:
            return "## NO HISTORICAL CONTEXT AVAILABLE\nNo similar deals found for contextual analysis."
        
        try:
            # Use provided LLM client or fallback to instance client
            client = llm_client or self.llm_client
            if not client:
                logger.error("No LLM client available for context generation")
                return "## ERROR\nLLM client not available for context generation."
            
            # Format similar deals data for LLM analysis
            deals_data = self._format_deals_for_analysis(similar_deals[:3])  # Top 3 deals
            
            # Format prompt with deals data
            formatted_prompt = self.prompt_template.format(similar_deals_data=deals_data)
            
            # Generate context using LLM
            logger.info(f"Generating LLM context for deal {deal_id} using {len(similar_deals)} similar deals")
            
            context = self._generate_context_with_llm(client, formatted_prompt)
            
            # Add footer
            context += "\n\n---\nUse this historical context to inform your sentiment analysis of the current deal."
            
            logger.info(f"Successfully generated LLM context for deal {deal_id}")
            return context
            
        except Exception as e:
            logger.error(f"Error generating LLM context for deal {deal_id}: {e}")
            return f"## ERROR\nFailed to generate historical context: {str(e)}"
    
    def _format_deals_for_analysis(self, similar_deals: List[Dict[str, Any]]) -> str:
        """
        Format similar deals data for LLM analysis
        
        Args:
            similar_deals: List of similar deals
            
        Returns:
            Formatted string with deal data
        """
        
        deals_text = []
        
        for i, deal in enumerate(similar_deals, 1):
            deal_id = deal.get('deal_id', f'Deal_{i}')
            metadata = deal.get('metadata', {})
            activities = deal.get('activities', [])
            
            # Extract key metadata
            outcome = metadata.get('outcome', 'unknown')
            deal_amount = metadata.get('deal_amount', 0)
            deal_stage = metadata.get('deal_stage', 'unknown')
            total_activities = metadata.get('total_activities', len(activities))
            
            # Format deal header
            deal_text = [f"### Deal {i} (ID: {deal_id})"]
            deal_text.append(f"- Outcome: {outcome}")
            deal_text.append(f"- Amount: ${deal_amount:,.2f}" if deal_amount > 0 else "- Amount: Not specified")
            deal_text.append(f"- Stage: {deal_stage}")
            deal_text.append(f"- Total Activities: {total_activities}")
            
            # Add activities (limited by count and character limit)
            activities_text = self._format_activities_for_deal(activities)
            if activities_text:
                deal_text.append("- Activities:")
                deal_text.append(activities_text)
            
            deals_text.append("\n".join(deal_text))
        
        return "\n\n".join(deals_text)
    
    def _format_activities_for_deal(self, activities: List[Dict[str, Any]]) -> str:
        """
        Format activities for a single deal with limits
        
        Args:
            activities: List of activities for the deal
            
        Returns:
            Formatted activities string (max 5 activities or 1500 chars)
        """
        
        if not activities:
            return "  No activities available"
        
        activity_lines = []
        total_chars = 0
        max_chars = 1500
        max_activities = 5
        
        for i, activity in enumerate(activities):
            if i >= max_activities:
                break
                
            activity_type = activity.get('activity_type', 'unknown').upper()
            content = activity.get('content', '').strip()
            
            if content:
                # Truncate content if too long
                # if len(content) > 200:
                #     content = content[:200] + "..."
                
                activity_line = f"  - {activity_type}: {content}"
                
                # Check character limit
                if total_chars + len(activity_line) > max_chars:
                    activity_lines.append("  - [Additional activities truncated...]")
                    break
                
                activity_lines.append(activity_line)
                total_chars += len(activity_line)
        
        return "\n".join(activity_lines) if activity_lines else "  No meaningful activities found"
    
    def _generate_context_with_llm(self, llm_client, prompt: str) -> str:
        """
        Generate context using LLM client
        
        Args:
            llm_client: LLM client instance
            prompt: Formatted prompt
            
        Returns:
            Generated context string
        """
        
        try:
            # Use the LLM client's provider to generate response
            # Adjust parameters for context generation (more focused, less creative)
            # logger.info(f"Context prompt: {prompt}")
            
            response = llm_client.provider.generate_response(
                prompt=prompt,
                max_tokens=2000  # Sufficient for structured context
            )
            
            if not response or not response.strip():
                return "## ERROR\nEmpty response from LLM"
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error calling LLM for context generation: {e}")
            raise
    
    def get_enabled_components(self) -> List[str]:
        """Get list of enabled components (for compatibility with existing interface)"""
        return ["LLMContextAnalysis"]
    
    def add_component(self, component):
        """Compatibility method - not applicable for LLM approach"""
        logger.warning("add_component() not applicable for LLM-based context builder")
    
    def remove_component(self, component_name: str):
        """Compatibility method - not applicable for LLM approach"""
        logger.warning("remove_component() not applicable for LLM-based context builder")

# Factory function for backward compatibility
def create_sales_context_builder(llm_client=None) -> LLMContextBuilder:
    """Create LLM context builder instance"""
    return LLMContextBuilder(llm_client=llm_client)

# Legacy class name alias for backward compatibility
RAGContextBuilder = LLMContextBuilder