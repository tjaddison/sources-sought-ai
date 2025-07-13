import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth/next'
import { DynamoDBClient, ScanCommand, QueryCommand } from '@aws-sdk/client-dynamodb'
import { marshall, unmarshall } from '@aws-sdk/util-dynamodb'

// Mock data for development - replace with actual DynamoDB queries
const mockStats = {
  opportunitiesFound: 47,
  responsesGenerated: 23,
  emailsSent: 156,
  pendingApprovals: 3
}

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

    // For now, return mock data
    // TODO: Replace with actual DynamoDB queries when infrastructure is ready
    const stats = await getDashboardStats()
    
    return NextResponse.json(stats)
  } catch (error) {
    console.error('Failed to fetch dashboard stats:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

async function getDashboardStats() {
  // Check if running in AWS environment with proper configuration
  const isDevelopment = process.env.NODE_ENV === 'development'
  const hasAwsConfig = process.env.AWS_REGION && process.env.DYNAMODB_TABLE_PREFIX
  
  if (isDevelopment || !hasAwsConfig) {
    // Return mock data for development
    return mockStats
  }

  try {
    // Initialize DynamoDB client
    const dynamoClient = new DynamoDBClient({
      region: process.env.AWS_REGION!
    })
    
    const tablePrefix = process.env.DYNAMODB_TABLE_PREFIX!
    const environment = process.env.ENVIRONMENT || 'dev'
    
    // Count opportunities found in the last 30 days
    const opportunitiesFound = await countRecentItems(
      dynamoClient,
      `${tablePrefix}-${environment}-opportunities`,
      'created_at',
      30
    )
    
    // Count responses generated
    const responsesGenerated = await countRecentItems(
      dynamoClient,
      `${tablePrefix}-${environment}-responses`,
      'created_at',
      30
    )
    
    // Count emails sent (from events table)
    const emailsSent = await countEventsByType(
      dynamoClient,
      `${tablePrefix}-${environment}-events`,
      'EMAIL_SENT',
      30
    )
    
    // Count pending approvals
    const pendingApprovals = await countPendingApprovals(
      dynamoClient,
      `${tablePrefix}-${environment}-approvals`
    )
    
    return {
      opportunitiesFound,
      responsesGenerated,
      emailsSent,
      pendingApprovals
    }
  } catch (error) {
    console.error('Failed to fetch stats from DynamoDB:', error)
    // Fallback to mock data if DynamoDB fails
    return mockStats
  }
}

async function countRecentItems(
  client: DynamoDBClient,
  tableName: string,
  dateField: string,
  daysBack: number
): Promise<number> {
  try {
    const cutoffDate = new Date()
    cutoffDate.setDate(cutoffDate.getDate() - daysBack)
    
    const command = new ScanCommand({
      TableName: tableName,
      FilterExpression: `#dateField >= :cutoffDate`,
      ExpressionAttributeNames: {
        '#dateField': dateField
      },
      ExpressionAttributeValues: marshall({
        ':cutoffDate': cutoffDate.toISOString()
      }),
      Select: 'COUNT'
    })
    
    const response = await client.send(command)
    return response.Count || 0
  } catch (error) {
    console.error(`Failed to count items in ${tableName}:`, error)
    return 0
  }
}

async function countEventsByType(
  client: DynamoDBClient,
  tableName: string,
  eventType: string,
  daysBack: number
): Promise<number> {
  try {
    const cutoffDate = new Date()
    cutoffDate.setDate(cutoffDate.getDate() - daysBack)
    
    const command = new ScanCommand({
      TableName: tableName,
      FilterExpression: `event_type = :eventType AND #timestamp >= :cutoffDate`,
      ExpressionAttributeNames: {
        '#timestamp': 'timestamp'
      },
      ExpressionAttributeValues: marshall({
        ':eventType': eventType,
        ':cutoffDate': cutoffDate.toISOString()
      }),
      Select: 'COUNT'
    })
    
    const response = await client.send(command)
    return response.Count || 0
  } catch (error) {
    console.error(`Failed to count events in ${tableName}:`, error)
    return 0
  }
}

async function countPendingApprovals(
  client: DynamoDBClient,
  tableName: string
): Promise<number> {
  try {
    const command = new ScanCommand({
      TableName: tableName,
      FilterExpression: `#status = :status`,
      ExpressionAttributeNames: {
        '#status': 'status'
      },
      ExpressionAttributeValues: marshall({
        ':status': 'pending'
      }),
      Select: 'COUNT'
    })
    
    const response = await client.send(command)
    return response.Count || 0
  } catch (error) {
    console.error(`Failed to count pending approvals in ${tableName}:`, error)
    return 0
  }
}