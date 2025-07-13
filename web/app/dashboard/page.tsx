'use client'

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { 
  ChartBarIcon, 
  DocumentTextIcon, 
  UserGroupIcon, 
  BellIcon,
  EyeIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline'

interface DashboardStats {
  opportunitiesFound: number
  responsesGenerated: number
  emailsSent: number
  pendingApprovals: number
}

interface RecentOpportunity {
  id: string
  title: string
  agency: string
  deadline: string
  matchScore: number
  status: 'pending_review' | 'approved' | 'submitted' | 'no_bid'
}

export default function DashboardPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [stats, setStats] = useState<DashboardStats>({
    opportunitiesFound: 0,
    responsesGenerated: 0,
    emailsSent: 0,
    pendingApprovals: 0
  })
  const [recentOpportunities, setRecentOpportunities] = useState<RecentOpportunity[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/')
      return
    }

    if (session) {
      loadDashboardData()
    }
  }, [session, status, router])

  const loadDashboardData = async () => {
    try {
      // Load dashboard statistics
      const statsResponse = await fetch('/api/dashboard/stats')
      const statsData = await statsResponse.json()
      setStats(statsData)

      // Load recent opportunities
      const oppsResponse = await fetch('/api/opportunities/recent')
      const oppsData = await oppsResponse.json()
      setRecentOpportunities(oppsData)
    } catch (error) {
      console.error('Failed to load dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  if (status === 'loading' || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="spinner border-brand-600"></div>
      </div>
    )
  }

  if (!session) {
    return null // Will redirect
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <h1 className="text-2xl font-bold text-gray-900">
              Sources Sought AI Dashboard
            </h1>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-600">
                Welcome, {session.user?.name}
              </span>
              <img
                src={session.user?.image || ''}
                alt={session.user?.name || ''}
                className="w-8 h-8 rounded-full"
              />
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            title="Opportunities Found"
            value={stats.opportunitiesFound}
            icon={<ChartBarIcon className="w-6 h-6" />}
            color="blue"
            trend="+12% this week"
          />
          <StatCard
            title="Responses Generated"
            value={stats.responsesGenerated}
            icon={<DocumentTextIcon className="w-6 h-6" />}
            color="green"
            trend="+8% this week"
          />
          <StatCard
            title="Emails Sent"
            value={stats.emailsSent}
            icon={<UserGroupIcon className="w-6 h-6" />}
            color="purple"
            trend="+15% this week"
          />
          <StatCard
            title="Pending Approvals"
            value={stats.pendingApprovals}
            icon={<BellIcon className="w-6 h-6" />}
            color="orange"
            urgent={stats.pendingApprovals > 0}
          />
        </div>

        {/* Recent Opportunities */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">
              Recent Opportunities
            </h3>
          </div>
          <div className="divide-y divide-gray-200">
            {recentOpportunities.map((opportunity) => (
              <OpportunityRow
                key={opportunity.id}
                opportunity={opportunity}
              />
            ))}
            {recentOpportunities.length === 0 && (
              <div className="px-6 py-12 text-center text-gray-500">
                No opportunities found yet. The system is monitoring SAM.gov for new Sources Sought notices.
              </div>
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="mt-8 grid md:grid-cols-3 gap-6">
          <QuickActionCard
            title="Review Opportunities"
            description="Review AI-discovered opportunities and approve responses"
            action="Review Now"
            href="/opportunities"
          />
          <QuickActionCard
            title="Manage Contacts"
            description="View and manage government contacts and relationships"
            action="View Contacts"
            href="/contacts"
          />
          <QuickActionCard
            title="System Settings"
            description="Configure company profile, keywords, and preferences"
            action="Settings"
            href="/settings"
          />
        </div>
      </div>
    </div>
  )
}

function StatCard({ 
  title, 
  value, 
  icon, 
  color, 
  trend, 
  urgent = false 
}: {
  title: string
  value: number
  icon: React.ReactNode
  color: 'blue' | 'green' | 'purple' | 'orange'
  trend?: string
  urgent?: boolean
}) {
  const colorClasses = {
    blue: 'bg-blue-500 text-blue-600',
    green: 'bg-green-500 text-green-600',
    purple: 'bg-purple-500 text-purple-600',
    orange: 'bg-orange-500 text-orange-600'
  }

  return (
    <div className={`bg-white rounded-lg shadow p-6 ${urgent ? 'ring-2 ring-orange-500' : ''}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value.toLocaleString()}</p>
          {trend && (
            <p className="text-sm text-gray-500 mt-1">{trend}</p>
          )}
        </div>
        <div className={`w-12 h-12 rounded-lg bg-opacity-10 flex items-center justify-center ${colorClasses[color]}`}>
          {icon}
        </div>
      </div>
    </div>
  )
}

function OpportunityRow({ opportunity }: { opportunity: RecentOpportunity }) {
  const statusConfig = {
    pending_review: { 
      label: 'Pending Review', 
      icon: ClockIcon, 
      color: 'text-yellow-600 bg-yellow-100' 
    },
    approved: { 
      label: 'Approved', 
      icon: CheckCircleIcon, 
      color: 'text-green-600 bg-green-100' 
    },
    submitted: { 
      label: 'Submitted', 
      icon: CheckCircleIcon, 
      color: 'text-blue-600 bg-blue-100' 
    },
    no_bid: { 
      label: 'No Bid', 
      icon: ExclamationTriangleIcon, 
      color: 'text-gray-600 bg-gray-100' 
    }
  }

  const status = statusConfig[opportunity.status]
  const StatusIcon = status.icon

  return (
    <div className="px-6 py-4 hover:bg-gray-50">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-gray-900 mb-1">
            {opportunity.title}
          </h4>
          <p className="text-sm text-gray-600">
            {opportunity.agency} • Deadline: {opportunity.deadline}
          </p>
          <div className="flex items-center mt-2">
            <span className="text-sm text-gray-500 mr-3">
              Match Score: {opportunity.matchScore}%
            </span>
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${status.color}`}>
              <StatusIcon className="w-3 h-3 mr-1" />
              {status.label}
            </span>
          </div>
        </div>
        <button className="btn btn-outline btn-sm">
          <EyeIcon className="w-4 h-4 mr-1" />
          View
        </button>
      </div>
    </div>
  )
}

function QuickActionCard({
  title,
  description,
  action,
  href
}: {
  title: string
  description: string
  action: string
  href: string
}) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-gray-600 mb-4">{description}</p>
      <a href={href} className="btn btn-primary btn-sm">
        {action}
      </a>
    </div>
  )
}