'use client'

import { useSession, signIn } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { 
  ChartBarIcon, 
  DocumentTextIcon, 
  UserGroupIcon, 
  BellIcon,
  ArrowRightIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline'

export default function HomePage() {
  const { data: session, status } = useSession()
  const router = useRouter()

  useEffect(() => {
    if (session) {
      router.push('/dashboard')
    }
  }, [session, router])

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="spinner border-brand-600"></div>
      </div>
    )
  }

  if (session) {
    return null // Will redirect to dashboard
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 via-white to-gov-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <h1 className="text-2xl font-bold text-gradient">
                Sources Sought AI
              </h1>
            </div>
            <button
              onClick={() => signIn('google')}
              className="btn btn-primary"
            >
              Sign In with Google
            </button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative px-4 sm:px-6 lg:px-8 py-24">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-4xl md:text-6xl font-bold text-gray-900 mb-6">
            Automate Your 
            <span className="text-gradient block mt-2">
              Sources Sought Response
            </span>
          </h1>
          <p className="text-xl text-gray-600 mb-8 max-w-3xl mx-auto leading-relaxed">
            Intelligent AI system that discovers government Sources Sought opportunities, 
            analyzes requirements, generates strategic responses, and manages relationships 
            to maximize your contracting success.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={() => signIn('google')}
              className="btn btn-primary btn-lg group"
            >
              Get Started
              <ArrowRightIcon className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </button>
            <button className="btn btn-secondary btn-lg">
              Watch Demo
            </button>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Complete Sources Sought Automation
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
              From discovery to submission, our AI agents handle every aspect of 
              the Sources Sought process while you focus on winning contracts.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            <FeatureCard
              icon={<ChartBarIcon className="w-8 h-8" />}
              title="Smart Discovery"
              description="AI monitors SAM.gov 24/7, finding relevant Sources Sought opportunities based on your capabilities and NAICS codes."
            />
            <FeatureCard
              icon={<DocumentTextIcon className="w-8 h-8" />}
              title="Intelligent Analysis"
              description="Advanced AI extracts requirements, performs gap analysis, and calculates win probability for strategic decision making."
            />
            <FeatureCard
              icon={<UserGroupIcon className="w-8 h-8" />}
              title="Response Generation"
              description="Creates compliant, strategic responses using proven templates and your company's past performance data."
            />
            <FeatureCard
              icon={<BellIcon className="w-8 h-8" />}
              title="Relationship Management"
              description="Tracks government contacts, manages follow-ups, and identifies teaming opportunities automatically."
            />
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section className="py-20 bg-gov-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="text-3xl font-bold text-gray-900 mb-6">
                Why Sources Sought Matter
              </h2>
              <p className="text-lg text-gray-600 mb-8">
                Sources Sought notices are posted 12-18 months before contract awards. 
                Early engagement gives you strategic advantages that competitors miss.
              </p>
              <div className="space-y-4">
                <BenefitItem text="Get on government radar before formal competition" />
                <BenefitItem text="Influence requirements to favor your capabilities" />
                <BenefitItem text="Trigger small business set-asides through 'Rule of Two'" />
                <BenefitItem text="Build relationships when it matters most" />
                <BenefitItem text="Access opportunities not in final solicitations" />
              </div>
            </div>
            <div className="lg:pl-8">
              <div className="bg-white p-8 rounded-2xl shadow-soft">
                <h3 className="text-xl font-semibold text-gray-900 mb-6">
                  Current Sources Sought Stats
                </h3>
                <div className="space-y-6">
                  <StatItem
                    number="3,700+"
                    label="Active Sources Sought on SAM.gov"
                  />
                  <StatItem
                    number="75%"
                    label="Reduction in response time"
                  />
                  <StatItem
                    number="18 months"
                    label="Average time before contract award"
                  />
                  <StatItem
                    number="100%"
                    label="Compliance rate with our system"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-brand-600">
        <div className="max-w-4xl mx-auto text-center px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl font-bold text-white mb-4">
            Ready to Transform Your Government Contracting?
          </h2>
          <p className="text-xl text-brand-100 mb-8">
            Join forward-thinking contractors who are already using AI to win more government contracts.
          </p>
          <button
            onClick={() => signIn('google')}
            className="btn bg-white text-brand-600 hover:bg-gray-100 btn-lg"
          >
            Start Your Free Trial
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-white py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h3 className="text-xl font-bold mb-4">Sources Sought AI</h3>
            <p className="text-gray-400 mb-4">
              Intelligent automation for government contracting success
            </p>
            <p className="text-sm text-gray-500">
              © 2024 Sources Sought AI. Built for government contractors.
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}

function FeatureCard({ icon, title, description }: {
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <div className="text-center group">
      <div className="bg-brand-100 w-16 h-16 rounded-xl flex items-center justify-center mx-auto mb-4 text-brand-600 group-hover:bg-brand-200 transition-colors">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-gray-600">{description}</p>
    </div>
  )
}

function BenefitItem({ text }: { text: string }) {
  return (
    <div className="flex items-start">
      <CheckCircleIcon className="w-6 h-6 text-success-500 mr-3 mt-0.5 flex-shrink-0" />
      <span className="text-gray-700">{text}</span>
    </div>
  )
}

function StatItem({ number, label }: { number: string; label: string }) {
  return (
    <div className="border-b border-gray-100 pb-4 last:border-b-0 last:pb-0">
      <div className="text-2xl font-bold text-brand-600">{number}</div>
      <div className="text-sm text-gray-600">{label}</div>
    </div>
  )
}