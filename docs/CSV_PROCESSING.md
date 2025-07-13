# SAM.gov CSV Processing

The Sources Sought AI system now processes opportunities directly from the SAM.gov Contract Opportunities CSV file instead of using the API. This provides more comprehensive data access and better reliability.

## Data Source

**CSV URL**: `https://s3.amazonaws.com/falextracts/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv`

**Update Frequency**: This file is updated regularly by SAM.gov with the latest contract opportunities data.

## CSV Schema

The CSV file contains the following columns:

| Column | Description |
|--------|-------------|
| NoticeId | Unique identifier for the opportunity |
| Title | Opportunity title |
| Sol# | Solicitation number |
| Department/Ind.Agency | Issuing agency |
| CGAC | Common Government-wide Accounting Classification |
| Sub-Tier | Agency sub-tier |
| FPDS Code | Federal Procurement Data System code |
| Office | Issuing office |
| AAC Code | Activity Address Code |
| PostedDate | Date opportunity was posted |
| Type | Notice type (e.g., Sources Sought) |
| BaseType | Base notice type |
| ArchiveType | Archive classification |
| ArchiveDate | Date opportunity will be archived |
| SetASideCode | Set-aside designation code |
| SetASide | Set-aside description |
| ResponseDeadLine | Deadline for responses |
| NaicsCode | NAICS codes (semicolon-separated) |
| ClassificationCode | Classification code |
| PopStreetAddress | Place of performance address |
| PopCity | Place of performance city |
| PopState | Place of performance state |
| PopZip | Place of performance ZIP |
| PopCountry | Place of performance country |
| Active | Whether opportunity is active |
| AwardNumber | Contract award number (if awarded) |
| AwardDate | Award date |
| Award$ | Award amount |
| Awardee | Award recipient |
| PrimaryContactTitle | Primary contact title |
| PrimaryContactFullname | Primary contact name |
| PrimaryContactEmail | Primary contact email |
| PrimaryContactPhone | Primary contact phone |
| PrimaryContactFax | Primary contact fax |
| SecondaryContactTitle | Secondary contact title |
| SecondaryContactFullname | Secondary contact name |
| SecondaryContactEmail | Secondary contact email |
| SecondaryContactPhone | Secondary contact phone |
| SecondaryContactFax | Secondary contact fax |
| OrganizationType | Organization type |
| State | Organization state |
| City | Organization city |
| ZipCode | Organization ZIP code |
| CountryCode | Country code |
| AdditionalInfoLink | Link to additional information |
| Link | Direct link to opportunity |
| Description | Opportunity description |

## Processing Workflow

### 1. Download CSV
The system downloads the latest CSV file from the SAM.gov S3 bucket.

### 2. Parse and Transform
Each CSV row is transformed into our opportunity data model:
- Date fields are parsed and standardized
- NAICS codes are split into arrays
- Contact information is structured
- Status is determined based on dates and active flag

### 3. Database Operations
For each opportunity:
- **New opportunities**: Inserted with `created_at` timestamp
- **Existing opportunities**: Updated if changes detected
- **Status management**: Set to archived if past ArchiveDate

### 4. Event Sourcing
All changes are logged to the events table:
- `OPPORTUNITY_CREATED` for new opportunities
- `OPPORTUNITY_UPDATED` for modified opportunities

### 5. Opportunity Matching
The OpportunityFinder agent scores opportunities based on:
- NAICS code match (30% weight)
- Keyword match in title/description (25% weight)  
- Agency preference (20% weight)
- Set-aside preference (15% weight)
- Opportunity value (10% weight)

## Usage Commands

### Basic Commands

```bash
# Test CSV parsing with sample data
make csv-test

# Download and show CSV sample
make csv-sample

# Process full CSV file
make csv-process

# Process CSV and run matching
make csv-match

# Full workflow (recommended)
make csv-full
```

### Advanced Usage

```bash
# Process with verbose output
python scripts/process_csv.py full --verbose

# Save results to file
python scripts/process_csv.py match --output results.json

# Test parsing only
python scripts/process_csv.py test
```

## API Endpoints

### Trigger CSV Processing
```http
POST /api/opportunities/process-csv
Authorization: Bearer <token>
```

### Check Processing Status
```http
GET /api/status/<task_id>
Authorization: Bearer <token>
```

## Configuration

### Environment Variables

```bash
# CSV processing settings
SAM_CSV_URL=https://s3.amazonaws.com/falextracts/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv
CSV_PROCESSING_BATCH_SIZE=1000

# AWS settings for data storage
AWS_REGION=us-east-1
DYNAMODB_TABLE_PREFIX=sources-sought-dev
```

### Company Matching Criteria

The matching algorithm uses configurable criteria in `OpportunityMatcher`:

```python
# Target NAICS codes
company_naics = [
    "541511",  # Custom Computer Programming Services
    "541512",  # Computer Systems Design Services
    "541513",  # Computer Facilities Management Services
    "541519",  # Other Computer Related Services
]

# Target keywords
keywords = [
    "software", "development", "cloud", "cybersecurity",
    "data", "analytics", "artificial intelligence"
]

# Preferred agencies
target_agencies = [
    "Department of Veterans Affairs",
    "General Services Administration",
    "Department of Defense"
]
```

## Data Quality & Validation

### Field Validation
- **NoticeId**: Required, used as unique identifier
- **Dates**: Multiple format support with UTC conversion
- **Currency**: Handles various currency formats
- **NAICS**: Splits semicolon-separated codes

### Error Handling
- Invalid rows are skipped with warnings
- Parsing errors are logged but don't stop processing
- Database errors are tracked in processing statistics

### Status Determination Logic
```python
if archive_date and current_date >= archive_date:
    status = "archived"
elif response_deadline and current_date > response_deadline:
    status = "expired"
elif active == "Yes":
    status = "active"
else:
    status = "inactive"
```

## Monitoring & Metrics

### Processing Statistics
- Total opportunities processed
- New insertions vs updates
- Processing time and error rates
- Match rates and priority distribution

### CloudWatch Metrics
- `OpportunitiesProcessed`
- `OpportunitiesMatched` 
- `HighPriorityOpportunities`
- `MatchRate`
- `ProcessingErrors`

### Event Sourcing
All processing activities are tracked in the events table for:
- Audit compliance
- Debugging and troubleshooting
- Historical analysis
- Performance optimization

## Performance Considerations

### Batch Processing
- Default batch size: 1000 opportunities
- Configurable via `CSV_PROCESSING_BATCH_SIZE`
- Background processing to avoid API timeouts

### Database Optimization
- Efficient update detection to minimize writes
- Batch operations where possible
- Indexed queries for fast lookups

### Memory Management
- Streaming CSV parsing for large files
- Batch processing to control memory usage
- Garbage collection between batches

## Troubleshooting

### Common Issues

**CSV Download Failures**
- Check internet connectivity
- Verify SAM.gov URL accessibility
- Check for rate limiting

**Parsing Errors**
- Validate CSV format matches expected schema
- Check for encoding issues
- Review error logs for specific row problems

**Database Errors**
- Verify DynamoDB table existence
- Check AWS credentials and permissions
- Monitor DynamoDB capacity and throttling

**Matching Issues**
- Review company criteria configuration
- Check keyword and NAICS code matching
- Validate opportunity data quality

### Debugging Commands

```bash
# Test with verbose logging
python scripts/process_csv.py test --verbose

# Check specific opportunity
aws dynamodb get-item --table-name sources-sought-dev-opportunities --key '{"id":{"S":"NOTICE_ID"}}'

# View recent events
aws dynamodb scan --table-name sources-sought-dev-events --filter-expression "event_type = :et" --expression-attribute-values '{":et":{"S":"OPPORTUNITY_CREATED"}}'
```

## Future Enhancements

### Planned Features
- Real-time CSV monitoring and processing
- Advanced duplicate detection
- Enhanced matching algorithms with ML
- Data quality scoring
- Automated data validation

### Integration Opportunities
- Direct SAM.gov API fallback
- Historical data analysis
- Predictive opportunity scoring
- Automated competitive intelligence