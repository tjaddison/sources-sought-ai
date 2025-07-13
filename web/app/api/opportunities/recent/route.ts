import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth/next'
import { DynamoDBClient, ScanCommand, QueryCommand } from '@aws-sdk/client-dynamodb'
import { marshall, unmarshall } from '@aws-sdk/util-dynamodb'

// Mock data for development
const mockOpportunities = [
  {
    id: 'opp-001',
    title: 'Cloud Infrastructure Services for Healthcare Systems',
    agency: 'Department of Veterans Affairs',
    deadline: '2024-02-15',
    matchScore: 92,
    status: 'pending_review'
  },
  {
    id: 'opp-002', 
    title: 'Cybersecurity Assessment and Monitoring Services',
    agency: 'Department of Homeland Security',
    deadline: '2024-02-20',
    matchScore: 85,
    status: 'approved'
  },
  {
    id: 'opp-003',
    title: 'Data Analytics Platform for Financial Operations',
    agency: 'General Services Administration',
    deadline: '2024-02-25',
    matchScore: 78,
    status: 'submitted'
  },
  {
    id: 'opp-004',
    title: 'Enterprise Software Development Services',
    agency: 'Department of Defense',
    deadline: '2024-03-01',
    matchScore: 73,
    status: 'pending_review'
  },
  {
    id: 'opp-005',
    title: 'Network Modernization and Support Services',
    agency: 'Department of Health and Human Services',
    deadline: '2024-03-05',
    matchScore: 45,
    status: 'no_bid'
  }
]

export async function GET(request: NextRequest) {
  try {
    // Check authentication
    const session = await getServerSession()
    if (!session) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }

    // Get query parameters
    const { searchParams } = new URL(request.url)
    const limit = parseInt(searchParams.get('limit') || '10')
    const offset = parseInt(searchParams.get('offset') || '0')

    // Fetch recent opportunities
    const opportunities = await getRecentOpportunities(limit, offset)
    
    return NextResponse.json(opportunities)
  } catch (error) {
    console.error('Failed to fetch recent opportunities:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

async function getRecentOpportunities(limit: number, offset: number) {
  // Check if running in AWS environment with proper configuration
  const isDevelopment = process.env.NODE_ENV === 'development'
  const hasAwsConfig = process.env.AWS_REGION && process.env.DYNAMODB_TABLE_PREFIX
  
  if (isDevelopment || !hasAwsConfig) {
    // Return mock data for development
    return mockOpportunities.slice(offset, offset + limit)
  }

  try {
    // Initialize DynamoDB client
    const dynamoClient = new DynamoDBClient({
      region: process.env.AWS_REGION!
    })
    
    const tablePrefix = process.env.DYNAMODB_TABLE_PREFIX!
    const environment = process.env.ENVIRONMENT || 'dev'
    const tableName = `${tablePrefix}-${environment}-opportunities`
    
    // Query recent opportunities ordered by creation date
    const command = new ScanCommand({
      TableName: tableName,
      FilterExpression: 'attribute_exists(created_at)',
      Limit: limit,
      ProjectionExpression: [
        'id',
        'title', 
        'agency',
        'response_deadline',
        'match_score',
        '#status',
        'priority',
        'created_at'
      ].join(', '),
      ExpressionAttributeNames: {
        '#status': 'status' // status is a reserved word in DynamoDB
      }
    })
    
    const response = await client.send(command)
    
    if (!response.Items) {
      return []
    }
    
    // Convert DynamoDB items to JavaScript objects
    const opportunities = response.Items.map(item => {
      const unmarshalled = unmarshall(item)
      
      return {
        id: unmarshalled.id,
        title: unmarshalled.title || 'Unknown Title',
        agency: unmarshalled.agency || 'Unknown Agency',
        deadline: formatDeadline(unmarshalled.response_deadline),
        matchScore: Math.round(unmarshalled.match_score || 0),
        status: mapStatus(unmarshalled.status),
        priority: unmarshalled.priority || 'medium',
        createdAt: unmarshalled.created_at
      }
    })
    
    // Sort by creation date (most recent first)
    opportunities.sort((a, b) => 
      new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    )
    
    return opportunities.slice(offset, offset + limit)
    
  } catch (error) {
    console.error('Failed to fetch opportunities from DynamoDB:', error)
    // Fallback to mock data if DynamoDB fails
    return mockOpportunities.slice(offset, offset + limit)
  }
}

function formatDeadline(deadline: string | undefined): string {
  if (!deadline) {
    return 'No deadline specified'
  }
  
  try {
    const date = new Date(deadline)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  } catch (error) {
    return deadline // Return original if parsing fails
  }
}

function mapStatus(status: string | undefined): string {
  const statusMap: Record<string, string> = {
    'discovered': 'pending_review',
    'analyzed': 'pending_review', 
    'response_generated': 'pending_review',
    'approved': 'approved',
    'submitted': 'submitted',
    'no_bid': 'no_bid',
    'rejected': 'no_bid'
  }
  
  return statusMap[status || ''] || 'pending_review'
}