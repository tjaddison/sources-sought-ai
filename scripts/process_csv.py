#!/usr/bin/env python3
"""
SAM.gov CSV processing management script.
Downloads and processes the SAM.gov Contract Opportunities CSV file.
"""

import asyncio
import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.utils.csv_processor import SAMCSVProcessor, process_sam_csv
from src.agents.opportunity_finder import run_opportunity_discovery
from src.utils.logger import get_logger


logger = get_logger("csv_management")


async def process_csv_only():
    """Process CSV file without matching"""
    logger.info("Processing SAM.gov CSV file...")
    
    try:
        stats = await process_sam_csv()
        
        print("\n=== CSV Processing Results ===")
        print(f"Total processed: {stats.get('total_processed', 0)}")
        print(f"Inserted: {stats.get('inserted', 0)}")
        print(f"Updated: {stats.get('updated', 0)}")
        print(f"Errors: {stats.get('errors', 0)}")
        print(f"Processing time: {stats.get('processing_time_seconds', 0):.2f} seconds")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error processing CSV: {e}")
        print(f"\nError: {e}")
        return None


async def process_and_match():
    """Process CSV and run opportunity matching"""
    logger.info("Processing CSV and running opportunity matching...")
    
    try:
        # First process the CSV
        csv_stats = await process_sam_csv()
        
        print("\n=== CSV Processing Results ===")
        print(f"Total processed: {csv_stats.get('total_processed', 0)}")
        print(f"Inserted: {csv_stats.get('inserted', 0)}")
        print(f"Updated: {csv_stats.get('updated', 0)}")
        print(f"Errors: {csv_stats.get('errors', 0)}")
        
        # Then run opportunity discovery/matching
        print("\n=== Running Opportunity Matching ===")
        discovery_results = await run_opportunity_discovery()
        
        if 'error' not in discovery_results:
            print(f"Matched opportunities: {discovery_results.get('matched_opportunities', 0)}")
            print(f"High priority: {discovery_results.get('high_priority_opportunities', 0)}")
            print(f"Processing time: {csv_stats.get('processing_time_seconds', 0):.2f} seconds")
        else:
            print(f"Error in matching: {discovery_results['error']}")
        
        return {
            'csv_stats': csv_stats,
            'discovery_results': discovery_results
        }
        
    except Exception as e:
        logger.error(f"Error in process and match: {e}")
        print(f"\nError: {e}")
        return None


async def download_csv_sample():
    """Download and show a sample of the CSV file"""
    logger.info("Downloading CSV sample...")
    
    try:
        processor = SAMCSVProcessor()
        csv_content = await processor.download_csv()
        
        # Show first few lines
        lines = csv_content.split('\n')
        print("\n=== CSV Sample (first 5 lines) ===")
        for i, line in enumerate(lines[:5]):
            print(f"{i+1}: {line}")
        
        print(f"\nTotal lines in CSV: {len(lines)}")
        print(f"CSV size: {len(csv_content)} characters")
        
        return True
        
    except Exception as e:
        logger.error(f"Error downloading CSV sample: {e}")
        print(f"\nError: {e}")
        return False


async def test_csv_parsing():
    """Test CSV parsing with a small sample"""
    logger.info("Testing CSV parsing...")
    
    sample_csv = '''NoticeId,Title,Sol#,Department/Ind.Agency,CGAC,Sub-Tier,FPDS Code,Office,AAC Code,PostedDate,Type,BaseType,ArchiveType,ArchiveDate,SetASideCode,SetASide,ResponseDeadLine,NaicsCode,ClassificationCode,PopStreetAddress,PopCity,PopState,PopZip,PopCountry,Active,AwardNumber,AwardDate,Award$,Awardee,PrimaryContactTitle,PrimaryContactFullname,PrimaryContactEmail,PrimaryContactPhone,PrimaryContactFax,SecondaryContactTitle,SecondaryContactFullname,SecondaryContactEmail,SecondaryContactPhone,SecondaryContactFax,OrganizationType,State,City,ZipCode,CountryCode,AdditionalInfoLink,Link,Description
TEST001,IT Modernization Services,,Department of Veterans Affairs,036,VA,70,VHA,36C,01/15/2024,Sources Sought,Sources Sought,,02/15/2024,,Small Business,02/01/2024,541511,,123 Main St,Washington,DC,20001,USA,Yes,,,,$0,,Contracting Officer,John Smith,john.smith@va.gov,202-555-0123,,,Jane Doe,jane.doe@va.gov,202-555-0124,,O,DC,Washington,20001,USA,https://sam.gov,https://sam.gov/opportunity/TEST001,The Department of Veterans Affairs seeks IT modernization services including cloud migration and cybersecurity enhancements.'''
    
    try:
        processor = SAMCSVProcessor()
        opportunities = processor.parse_csv_content(sample_csv)
        
        print("\n=== Parsed Opportunities ===")
        for opp in opportunities:
            print(f"ID: {opp['id']}")
            print(f"Title: {opp['title']}")
            print(f"Agency: {opp['agency']}")
            print(f"Status: {opp['status']}")
            print(f"NAICS: {opp['naics_codes']}")
            print(f"Set-aside: {opp['set_aside']}")
            print("---")
        
        print(f"Total parsed: {len(opportunities)}")
        return True
        
    except Exception as e:
        logger.error(f"Error testing CSV parsing: {e}")
        print(f"\nError: {e}")
        return False


def print_stats_summary(stats):
    """Print a summary of processing statistics"""
    if not stats:
        print("No statistics available")
        return
    
    print("\n" + "="*50)
    print("PROCESSING SUMMARY")
    print("="*50)
    
    if 'csv_stats' in stats:
        csv_stats = stats['csv_stats']
        print(f"CSV Processing:")
        print(f"  Total opportunities: {csv_stats.get('total_processed', 0):,}")
        print(f"  New insertions: {csv_stats.get('inserted', 0):,}")
        print(f"  Updates: {csv_stats.get('updated', 0):,}")
        print(f"  Errors: {csv_stats.get('errors', 0):,}")
        print(f"  Processing time: {csv_stats.get('processing_time_seconds', 0):.2f}s")
    
    if 'discovery_results' in stats:
        discovery = stats['discovery_results']
        if 'error' not in discovery:
            print(f"\nOpportunity Matching:")
            print(f"  Matched opportunities: {discovery.get('matched_opportunities', 0):,}")
            print(f"  High priority: {discovery.get('high_priority_opportunities', 0):,}")
            
            top_matches = discovery.get('top_matches', [])
            if top_matches:
                print(f"\nTop 3 Matches:")
                for i, match in enumerate(top_matches[:3], 1):
                    print(f"  {i}. {match.get('title', 'Unknown')} (Score: {match.get('match_score', 0):.1f})")


async def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="SAM.gov CSV Processing Management")
    parser.add_argument(
        "action",
        choices=["process", "match", "sample", "test", "full"],
        help="Action to perform"
    )
    parser.add_argument(
        "--output",
        help="Output file for results (JSON format)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel("DEBUG")
    
    print(f"Starting SAM.gov CSV {args.action}...")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Execute the requested action
    results = None
    
    if args.action == "process":
        results = await process_csv_only()
    elif args.action == "match":
        results = await process_and_match()
    elif args.action == "sample":
        success = await download_csv_sample()
        results = {"success": success}
    elif args.action == "test":
        success = await test_csv_parsing()
        results = {"success": success}
    elif args.action == "full":
        results = await process_and_match()
    
    # Print summary
    if results:
        print_stats_summary(results)
    
    # Save results to file if requested
    if args.output and results:
        try:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\nResults saved to: {args.output}")
        except Exception as e:
            print(f"Error saving results: {e}")
    
    print(f"\nCompleted at: {datetime.now().isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())