import { api } from './client'
import type { MetaData, RecommendResult, Competitor, WatchKeyword, SystemStatus, AdminUser, RegionStat, IndustryStat, ClusterResult, ModelInfo, IndustryFilterItem, MyBidAnalysis, OverviewStatsWithChange, CollectionLogOut, BidRangeResponse, SrateTrendResponse, TopSrateTrend, PrismResponse, CompetitorZoneResponse, BidRecommendItem, JointPartnersResponse, CollectorStatus, BidSearchItem, FinalRecommendResult } from '../types'

type KeywordUpdateBody = Partial<Pick<WatchKeyword, 'keyword' | 'kw_type' | 'is_active' | 'note'>>

// -- 인증 --------------------------------------------------

export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }).then((r) => r.data),
  me: () => api.get('/auth/me').then((r) => r.data),
}

// -- 입찰 --------------------------------------------------

export const bidsApi = {
  list: (params: {
    keyword?: string
    page?: number
    size?: number
    status?: string
    sort_by?: string
    agency_id?: number
    industry_id?: number
    region_id?: number
    date_from?: string
    date_to?: string
  }) =>
    api.get('/bids', { params }).then((r) => r.data),
  detail: (id: number) =>
    api.get(`/bids/${id}`).then((r) => r.data),
  similar: (id: number, topK = 8) =>
    api.get(`/bids/${id}/similar`, { params: { top_k: topK } }).then((r) => r.data),
  keywordMatches: () =>
    api.get(`/bids/keyword-matches`).then((r) => r.data),
  meta: (): Promise<MetaData> =>
    api.get('/bids/meta').then((r) => r.data),
  bookmarks: (params?: { page?: number; size?: number }) =>
    api.get('/bids/bookmarks', { params }).then((r) => r.data),
  addBookmark: (id: number) =>
    api.post(`/bids/${id}/bookmark`).then((r) => r.data),
  removeBookmark: (id: number) =>
    api.delete(`/bids/${id}/bookmark`).then((r) => r.data),
  opportunityScore: (id: number): Promise<import('../types').OpportunityScore> =>
    api.get(`/bids/${id}/opportunity-score`).then((r) => r.data),
  recommended: (limit = 5): Promise<BidRecommendItem[]> =>
    api.get('/bids/recommended', { params: { limit } }).then((r) => r.data),
  jointPartners: (bidId: number, userTrack: number, participationRate = 0.6): Promise<JointPartnersResponse> =>
    api.get(`/bids/${bidId}/joint-partners`, { params: { user_track: userTrack, participation_rate: participationRate } }).then((r) => r.data),
  search: (announcementNo: string, limit = 10): Promise<BidSearchItem[]> =>
    api.get('/bids/search', { params: { announcement_no: announcementNo, limit } }).then((r) => r.data),
  finalRecommend: (bidId: number): Promise<FinalRecommendResult> =>
    api.get(`/bids/${bidId}/final-recommend`).then((r) => r.data),
}

// -- 추천 --------------------------------------------------

export const recommendApi = {
  recommend: (body: {
    industry_id: number
    region_id: number
    agency_id: number
    base_amount: number
    a_value?: number
    construction_period?: number
    known_competitor_ids?: number[]
  }): Promise<RecommendResult> =>
    api.post('/recommend', body).then((r) => r.data),
  history: () => api.get('/recommend/history').then((r) => r.data),
  retrain: () => api.post('/recommend/retrain').then((r) => r.data),
  recommendV2: (body: { agency_id: number; industry_id: number; region_id: number; base_amount: number; min_bid_rate?: number; bid_open_date?: string; a_value?: number; construction_period?: number; known_competitor_ids?: number[] }) =>
    api.post('/recommend/v2', body).then((r) => r.data),
  retrainAssessment: () => api.post('/recommend/v2/retrain-assessment').then((r) => r.data),
  srateStats: (agencyId?: number, industryId?: number) =>
    api.get('/recommend/v2/srate-stats', { params: { agency_id: agencyId, industry_id: industryId } }).then((r) => r.data),
  yegaFrequency: (baseAmount: number, aValue?: number, agencyId?: number): Promise<import('../types').YegaFrequencyResult> =>
    api.get('/recommend/yega-frequency', { params: { base_amount: baseAmount, a_value: aValue, agency_id: agencyId } }).then((r) => r.data),
  bidRange: (params: { base_amount: number; industry_id?: number; agency_id?: number; region_id?: number }): Promise<BidRangeResponse> =>
    api.get('/recommend/bid-range', { params }).then((r) => r.data),
  prism: (body: { agency_id: number; industry_id: number; region_id: number; base_amount: number; min_bid_rate?: number }): Promise<PrismResponse> =>
    api.post('/recommend/prism', body).then((r) => r.data),
}

// -- 경쟁사 --------------------------------------------------

export const competitorsApi = {
  list: (params?: { keyword?: string; page?: number; size?: number; risk_level?: string }) =>
    api.get('/competitors', { params }).then((r) => r.data),
  detail: (id: number): Promise<Competitor> =>
    api.get(`/competitors/${id}`).then((r) => r.data),
  timeline: (id: number, months = 12) =>
    api.get(`/competitors/${id}/timeline`, { params: { months } }).then((r) => r.data),
  wins: (id: number, limit = 50) =>
    api.get(`/competitors/${id}/wins`, { params: { limit } }).then((r) => r.data),
  pattern: (id: number) =>
    api.get(`/competitors/${id}/pattern`).then((r) => r.data),
  compare: (ids: number[]) =>
    api.get('/competitors/compare', { params: { ids: ids.join(',') } }).then((r) => r.data),
  zones: (id: number, days = 90): Promise<CompetitorZoneResponse> =>
    api.get(`/competitors/${id}/zones`, { params: { days } }).then((r) => r.data),
}

// -- 통계 --------------------------------------------------

export const statsApi = {
  overview: (months = 12): Promise<OverviewStatsWithChange> =>
    api.get('/stats/overview', { params: { months } }).then((r) => r.data),
  agencies: (months = 12) =>
    api.get('/stats/agencies', { params: { months } }).then((r) => r.data),
  regions: (months = 12): Promise<RegionStat[]> =>
    api.get('/stats/regions', { params: { months } }).then((r) => r.data),
  industries: (months = 12): Promise<IndustryStat[]> =>
    api.get('/stats/industries', { params: { months } }).then((r) => r.data),
  rateDistribution: (params?: { industry_id?: number; months?: number }) =>
    api.get('/stats/rate-distribution', { params }).then((r) => r.data),
  srateDistribution: (params?: { agency_id?: number; industry_id?: number; months?: number }): Promise<import('../types').SrateDistributionResult> =>
    api.get('/stats/srate-distribution', { params }).then((r) => r.data),
  heatmap: (months = 24) =>
    api.get('/stats/heatmap', { params: { months } }).then((r) => r.data),
  cluster: (params?: { industry_id?: number; months?: number; k?: number }): Promise<ClusterResult> =>
    api.get('/stats/cluster', { params }).then((r) => r.data),
  modelInfo: (months = 12): Promise<ModelInfo> =>
    api.get('/stats/model-info', { params: { months } }).then((r) => r.data),
  srateTrend: (agencyId?: number, industryId?: number): Promise<SrateTrendResponse> =>
    api.get('/stats/srate-trend', { params: { agency_id: agencyId, industry_id: industryId } }).then((r) => r.data),
  topSrateTrends: (limit = 3): Promise<TopSrateTrend[]> =>
    api.get('/stats/top-srate-trends', { params: { limit } }).then((r) => r.data),
}

// -- 키워드 --------------------------------------------------

export const keywordsApi = {
  list: (): Promise<WatchKeyword[]> =>
    api.get('/keywords').then((r) => r.data),
  create: (body: { keyword: string; kw_type?: string; note?: string }): Promise<WatchKeyword> =>
    api.post('/keywords', body).then((r) => r.data),
  update: (id: number, body: KeywordUpdateBody): Promise<WatchKeyword> =>
    api.put(`/keywords/${id}`, body).then((r) => r.data),
  delete: (id: number): Promise<void> =>
    api.delete(`/keywords/${id}`).then((r) => r.data),
}

// -- 관리자 --------------------------------------------------

export const adminApi = {
  users: (): Promise<AdminUser[]> =>
    api.get('/admin/users').then((r) => r.data),
  createUser: (body: { email: string; password: string; name: string; role: string; department?: string }) =>
    api.post('/admin/users', body).then((r) => r.data),
  updateUser: (id: number, body: Partial<{ name: string; role: string; department: string; is_active: boolean; password: string }>) =>
    api.put(`/admin/users/${id}`, body).then((r) => r.data),
  deleteUser: (id: number) =>
    api.delete(`/admin/users/${id}`).then((r) => r.data),
  systemStatus: (): Promise<SystemStatus> =>
    api.get('/admin/system-status').then((r) => r.data),
  industryFilters: (): Promise<IndustryFilterItem[]> =>
    api.get('/admin/industries').then((r) => r.data),
  updateIndustryFilters: (active_ids: number[]) =>
    api.put('/admin/industries/filters', { active_ids }).then((r) => r.data),
  collectionLogs: (days = 7): Promise<CollectionLogOut[]> =>
    api.get('/admin/collection-logs', { params: { days } }).then((r) => r.data),
  triggerCollect: (collectType: 'all' | 'notices' | 'results'): Promise<{ message: string }> =>
    api.post('/admin/collect/trigger', null, { params: { collect_type: collectType } }).then((r) => r.data),
  inpo21cStatus: (): Promise<{ has_cookie: boolean; cookie_valid: boolean; status: string; message: string }> =>
    api.get('/admin/inpo21c/status').then((r) => r.data),
  triggerInpo21cCollect: (maxPages = 4): Promise<{ message: string }> =>
    api.post('/admin/inpo21c/collect', null, { params: { max_pages: maxPages } }).then((r) => r.data),
  collectorStatus: (): Promise<CollectorStatus> =>
    api.get('/admin/collector-status').then((r) => r.data),
}

// -- 투찰 이력 --------------------------------------------------

export const myBidsApi = {
  list: (params?: { result?: string; page?: number; size?: number }) =>
    api.get('/my-bids', { params }).then((r) => r.data),
  stats: () => api.get('/my-bids/stats').then((r) => r.data),
  analysis: (): Promise<MyBidAnalysis> =>
    api.get('/my-bids/analysis').then((r) => r.data),
  create: (body: {
    title: string; agency_name?: string; bid_date?: string
    base_amount?: number; submitted_rate: number; recommendation_rate?: number; note?: string; bid_id?: number
  }) => api.post('/my-bids', body).then((r) => r.data),
  update: (id: number, body: { result?: string; actual_winner_rate?: number; note?: string; submitted_rate?: number }) =>
    api.put(`/my-bids/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/my-bids/${id}`).then((r) => r.data),
  defeatAnalysis: (): Promise<import('../types').DefeatAnalysis> =>
    api.get('/my-bids/defeat-analysis').then((r) => r.data),
  gapAnalysis: (): Promise<import('../types').GapAnalysisResponse> =>
    api.get('/my-bids/gap-analysis').then((r) => r.data),
  winPattern: (): Promise<import('../types').WinPattern> =>
    api.get('/my-bids/win-pattern').then((r) => r.data),
}

// -- 발주기관 --------------------------------------------------

export const agenciesApi = {
  list: (params?: { q?: string; page?: number; size?: number }) =>
    api.get('/agencies', { params }).then((r) => r.data),
  analysis: (id: number) =>
    api.get(`/agencies/${id}/analysis`).then((r) => r.data),
  srateHistogram: (id: number, months = 12): Promise<import('../types').SrateHistogramResponse> =>
    api.get(`/agencies/${id}/srate-histogram`, { params: { months } }).then((r) => r.data),
  recentResults: (id: number, limit = 20): Promise<import('../types').AgencyRecentResultsResponse> =>
    api.get(`/agencies/${id}/recent-results`, { params: { limit } }).then((r) => r.data),
}



