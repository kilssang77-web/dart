import { api } from './client'
import type { MetaData, RecommendResult, Competitor, WatchKeyword, SystemStatus, AdminUser, RegionStat, IndustryStat, ClusterResult, ModelInfo, IndustryFilterItem, MyBidAnalysis, OverviewStatsWithChange, CollectionLogOut, BidRangeResponse, SrateTrendResponse, TopSrateTrend, PrismResponse, CompetitorZoneResponse, BidRecommendItem, JointPartnersResponse, JointSimRequest, JointSimResponse, CollectorStatus, BidSearchItem, FinalRecommendResult } from '../types'

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
    yega_method?: string
    contract_method?: string
    base_amount_min?: number
    base_amount_max?: number
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
  jointSimulate: (bidId: number, body: JointSimRequest): Promise<JointSimResponse> =>
    api.post(`/bids/${bidId}/joint-simulate`, body).then((r) => r.data),
  inpoParticipants: (bidId: number): Promise<import('../types').InpoParticipant[]> =>
    api.get(`/bids/${bidId}/inpo-participants`).then((r) => r.data),
  rivalRadar: (bidId: number, topK = 15): Promise<import('../types').RivalRadarResponse> =>
    api.get(`/bids/${bidId}/rival-radar`, { params: { top_k: topK } }).then((r) => r.data),
  actualWinZones: (bidId: number): Promise<import('../types').ActualWinZonesResponse> =>
    api.get(`/bids/${bidId}/actual-win-zones`).then((r) => r.data),
  prismHistogram: (bidId: number, period: '12M' | '24M' | '48M' = '24M'): Promise<import('../types').PrismHistogramResponse> =>
    api.get(`/bids/${bidId}/prism-histogram`, { params: { period } }).then((r) => r.data),
  bestRate: (bidId: number, period: '12M' | '24M' | '48M' = '24M'): Promise<import('../types').BestRateResponse> =>
    api.get(`/bids/${bidId}/best-rate`, { params: { period } }).then((r) => r.data),
  hotZones: (bidId: number, period: '12M' | '24M' | '48M' = '24M'): Promise<import('../types').HotZoneResponse> =>
    api.get(`/bids/${bidId}/hot-zones`, { params: { period } }).then((r) => r.data),

  upcomingOpenings: (days = 7): Promise<import('../types').UpcomingOpeningsResponse> =>
    api.get('/bids/upcoming-openings', { params: { days } }).then((r) => r.data),
  yega: (bidId: number): Promise<import('../types').InpoYegaResponse> =>
    api.get(`/bids/${bidId}/yega`).then((r) => r.data),
  participantStats: (bidId: number): Promise<import('../types').ParticipantStats> =>
    api.get(`/bids/${bidId}/participant-stats`).then((r) => r.data),
}

// -- 시장 인텔리전스 --------------------------------------------------

export const marketIntelApi = {
  agencyHeatmap: (months = 12, topN = 20): Promise<import('../types').MarketIntelHeatmap> =>
    api.get('/market-intel/agency-heatmap', { params: { months, top_n: topN } }).then((r) => r.data),
  winnerTrend: (agencyName?: string): Promise<{ agency_name: string | null; trend: import('../types').WinnerTrendItem[] }> =>
    api.get('/market-intel/winner-trend', { params: { agency_name: agencyName } }).then((r) => r.data),
  topWinners: (agencyName?: string, topN = 10): Promise<import('../types').TopWinnerItem[]> =>
    api.get('/market-intel/top-winners', { params: { agency_name: agencyName, top_n: topN } }).then((r) => r.data),
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
  recommendV2: (body: { agency_id: number; industry_id: number; region_id: number; base_amount: number; min_bid_rate?: number; bid_open_date?: string; a_value?: number; construction_period?: number; known_competitor_ids?: number[]; bid_id?: number }) =>
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
  predict: (id: number, bidId: number): Promise<import('../types').CompetitorPredictResponse> =>
    api.get(`/competitors/${id}/predict`, { params: { bid_id: bidId } }).then((r) => r.data),
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
  collectionLogDetail: (id: number): Promise<CollectionLogOut> =>
    api.get(`/admin/collection-logs/${id}`).then((r) => r.data),
  triggerCollect: (collectType: 'all' | 'notices' | 'results'): Promise<{ message: string }> =>
    api.post('/admin/collect/trigger', null, { params: { collect_type: collectType } }).then((r) => r.data),
  inpo21cStatus: (): Promise<{ has_cookie: boolean; cookie_valid: boolean; has_autologin: boolean; can_collect: boolean; status: string; message: string }> =>
    api.get('/admin/inpo21c/status').then((r) => r.data),
  triggerInpo21cCollect: (maxPages = 4): Promise<{ message: string }> =>
    api.post('/admin/inpo21c/collect', null, { params: { max_pages: maxPages } }).then((r) => r.data),
  inpo21cProgress: (): Promise<{
    running: boolean; job_type: string | null
    page: number; max_pages: number; total_pages: number
    bids: number; participants: number; yega: number; skipped: number
    pct: number; started_at: string | null; finished_at: string | null; error: string | null
  }> =>
    api.get('/admin/inpo21c/collect-progress').then((r) => r.data),
  collectorStatus: (): Promise<CollectorStatus> =>
    api.get('/admin/collector-status').then((r) => r.data),
  mlCalibration: (): Promise<import('@/types').MlCalibration> =>
    api.get('/admin/ml/calibration').then((r) => r.data),
  collusionScan: (days = 30, limit = 100): Promise<import('@/types').CollusionScanResponse> =>
    api.get('/admin/ml/collusion-scan', { params: { days, limit } }).then((r) => r.data),
  collusionScanOne: (announcementNo: string): Promise<import('@/types').CollusionResult> =>
    api.get(`/admin/ml/collusion-scan/${announcementNo}`).then((r) => r.data),
  trainWinProb: (): Promise<{ status: string; message: string }> =>
    api.post('/admin/ml/train-win-prob').then((r) => r.data),
  winProbStatus: (): Promise<{
    trained: boolean
    best_iteration?: number
    n_train?: number
    n_pos?: number
    auc?: number
    pr_auc?: number
    lift_at_10?: number
    feature_importance?: Record<string, number>
    feature_cols?: string[]
    trained_at?: number
    trained_at_str?: string
    model_path?: string
  }> =>
    api.get('/admin/ml/win-prob-status').then((r) => r.data),
  retrainAll: (): Promise<{ status: string; message: string }> =>
    api.post('/admin/ml/retrain').then((r) => r.data),
  syncInpo21cToBids: (): Promise<{ updated_base_amount: number; updated_open_date: number; updated_participants: number }> =>
    api.post('/admin/sync-inpo21c-to-bids').then((r) => r.data),
  migrateJournalToExecutions: (): Promise<{ status: string; created: number; skipped: number }> =>
    api.post('/admin/journal/migrate-to-executions').then((r) => r.data),
  schedulerJobs: (): Promise<import('@/types').SchedulerJob[]> =>
    api.get('/admin/scheduler-jobs').then((r) => r.data),
  collectionStats: (days = 30): Promise<import('@/types').CollectionTypeStat[]> =>
    api.get('/admin/collection-stats', { params: { days } }).then((r) => r.data),
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
    announcement_no?: string; actual_winner_rate?: number; result?: string
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
  exportExcel: (): Promise<Blob> =>
    api.get('/my-bids/export/excel', { responseType: 'blob' }).then((r) => r.data),
  importExcel: (file: File): Promise<{ imported: number; skipped: number; errors: string[]; details: string[] }> => {
    const fd = new FormData(); fd.append('file', file)
    return api.post('/my-bids/import/excel', fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data)
  },
  inpoRank: (announcementNo: string): Promise<import('../types').SekihaiInfo> =>
    api.get('/my-bids/inpo-rank', { params: { announcement_no: announcementNo } }).then((r) => r.data),
  inpoRankBatch: (announcementNos: string[]): Promise<Record<string, import('../types').SekihaiInfo>> =>
    api.post('/my-bids/inpo-rank-batch', { announcement_nos: announcementNos }).then((r) => r.data),
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
  yegaPattern: (id: number): Promise<import('../types').AgencyYegaPattern> =>
    api.get(`/agencies/${id}/yega-pattern`).then((r) => r.data),
  strategy: (id: number, params?: { industry_code?: string; period_months?: number }): Promise<import('../types').AgencyStrategy> =>
    api.get(`/agencies/${id}/strategy`, { params }).then((r) => r.data),
  rebuildStrategies: () =>
    api.post('/agencies/rebuild-strategies').then((r) => r.data),
}

// ── 수주율 최적화 시스템 ──────────────────────────────────────────

export const companyApi = {
  getProfile: () =>
    api.get('/company/profile').then((r) => r.data),
  upsertProfile: (body: Record<string, unknown>) =>
    api.put('/company/profile', body).then((r) => r.data),
  bondStatus: () =>
    api.get('/company/bond-status').then((r) => r.data),
}

export const selectionApi = {
  evaluate: (bidId: number) =>
    api.post(`/selection/evaluate/${bidId}`).then((r) => r.data),
  goList: (days = 7) =>
    api.get('/selection/go-list', { params: { days } }).then((r) => r.data),
  evaluateBatch: (bidIds: number[]) =>
    api.post('/selection/evaluate-batch', { bid_ids: bidIds }).then((r) => r.data),
}

export const strategyApi = {
  singleRecommend: (body: {
    bid_id?: number
    base_amount: number
    agency_id: number
    industry_id?: number
    region_id?: number
    min_bid_rate?: number
    our_share_rate?: number
  }) => api.post('/strategy/recommend', body).then((r) => r.data),
}

export const outcomesApi = {
  record: (body: {
    bid_id: number
    submitted_rate: number
    result: 'WON' | 'LOST' | 'DISQUALIFIED'
    actual_srate?: number
    winner_rate?: number
    our_rank?: number
    total_bidders?: number
    disqualify_reason?: string
    bid_decision_id?: number
  }) => api.post('/outcomes', body).then((r) => r.data),
  list: (params?: { limit?: number; result?: string }) =>
    api.get('/outcomes', { params }).then((r) => r.data),
  stats: () =>
    api.get('/outcomes/stats').then((r) => r.data),
}

export const kpiApi = {
  dashboard: (periodType: 'DAILY' | 'WEEKLY' | 'MONTHLY' = 'MONTHLY') =>
    api.get('/kpi/dashboard', { params: { period_type: periodType } }).then((r) => r.data),
  forceSnapshot: (periodType = 'MONTHLY') =>
    api.post('/kpi/snapshot', null, { params: { period_type: periodType } }).then((r) => r.data),
}

export const portfolioApi = {
  optimize: (bidIds: number[]) =>
    api.post('/portfolio/optimize', { bid_ids: bidIds }).then((r) => r.data),
  active: () =>
    api.get('/portfolio/active').then((r) => r.data),
}

// -- 알림 --------------------------------------------------


export const notificationsApi = {
  list: (params?: { unread_only?: boolean; limit?: number }): Promise<import('../types').NotificationListResponse> =>
    api.get('/notifications', { params }).then((r) => r.data),
  unreadCount: (): Promise<{ count: number }> =>
    api.get('/notifications/unread-count').then((r) => r.data),
  markRead: (id: number): Promise<void> =>
    api.post(`/notifications/${id}/read`).then(() => undefined),
  markAllRead: (): Promise<void> =>
    api.post('/notifications/read-all').then(() => undefined),
}

// -- 투찰 실행 관리 ------------------------------------------

export const executionsApi = {
  list: (params?: {
    status?: string
    page?: number
    size?: number
  }): Promise<import('../types').ExecutionListResponse> =>
    api.get('/executions', { params }).then((r) => r.data),

  summary: (): Promise<import('../types').ExecutionSummary> =>
    api.get('/executions/summary').then((r) => r.data),

  get: (id: number): Promise<import('../types').BidExecution> =>
    api.get(`/executions/${id}`).then((r) => r.data),

  create: (data: {
    title: string
    agency_name?: string
    base_amount?: number
    bid_open_date?: string
    announcement_no?: string
    industry_name?: string
    floor_rate?: number
    a_value?: number
    recommended_rate?: number
    note?: string
  }): Promise<import('../types').BidExecution> =>
    api.post('/executions', data).then((r) => r.data),

  update: (id: number, data: Partial<{
    status: string
    decision_reason: string
    submitted_rate: number
    submitted_amount: number
    floor_rate: number
    a_value: number
    submitted_at: string
    result_rank: number
    total_bidders: number
    winner_rate: number
    winner_amount: number
    winner_name: string
    winner_biz_no: string
    opened_at: string
    note: string
  }>): Promise<import('../types').BidExecution> =>
    api.patch(`/executions/${id}`, data).then((r) => r.data),

  delete: (id: number): Promise<void> =>
    api.delete(`/executions/${id}`).then(() => undefined),

  defeatAnalysis: (id: number): Promise<import('../types').DefeatAnalysis | null> =>
    api.get(`/executions/${id}/defeat-analysis`).then((r) => r.data),

  defeatSummary: (): Promise<import('../types').DefeatSummaryResponse> =>
    api.get('/executions/defeat-summary').then((r) => r.data),

  importSucview: (file: File): Promise<import('../types').SucviewImportResult> => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/executions/import/sucview', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  importInpoHistory: (file: File): Promise<import('../types').SucviewImportResult> => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/executions/import/inpo-history', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  ourCompetitors: (limit?: number): Promise<import('../types').OurCompetitor[]> =>
    api.get('/executions/our-competitors', { params: { limit } }).then((r) => r.data),

  agencyFreq: (
    agencyId: number,
    params?: { industry_code?: string; period?: string }
  ): Promise<import('../types').AgencyFreqResponse> =>
    api.get(`/executions/agency-freq/${agencyId}`, { params }).then((r) => r.data),
}

// -- 백테스트 ---------------------------------------------

export const backtestApi = {
  run: (months?: number): Promise<import('../types').BacktestResult> =>
    api.get('/backtest', { params: { months } }).then((r) => r.data),
}

// -- 투찰 결정 ---------------------------------------------

export const decisionApi = {
  context: (bidId: number): Promise<import('../types').BidContext> =>
    api.get(`/bids/${bidId}/bid-context`).then((r) => r.data),

  simulate: (bidId: number, req: import('../types').SimulateBidRequest): Promise<import('../types').SimulateBidResponse> =>
    api.post(`/bids/${bidId}/simulate-bid`, req).then((r) => r.data),

  agencyWinHistogram: (bidId: number): Promise<import('../types').AgencyWinHistogram> =>
    api.get(`/bids/${bidId}/agency-win-histogram`).then((r) => r.data),

  winProbCurve: (bidId: number): Promise<import('../types').WinProbCurve> =>
    api.get(`/bids/${bidId}/win-prob-curve`).then((r) => r.data),

  competitorPrediction: (bidId: number, topN = 15): Promise<import('../types').CompetitorPredictionResponse> =>
    api.get(`/bids/${bidId}/competitor-prediction`, { params: { top_n: topN } }).then((r) => r.data),

  searchBids: (keyword: string, limit = 10) =>
    api.get('/bids/search', { params: { q: keyword, limit } }).then((r) => r.data),

  positionAnalysis: (bidId: number): Promise<import('../types').PositionAnalysisResponse> =>
    api.get(`/bids/${bidId}/position-analysis`).then((r) => r.data),

  quickDecision: (bidId: number): Promise<import('../types').QuickDecisionResponse> =>
    api.get(`/bids/${bidId}/quick-decision`).then((r) => r.data),

  pqFloor: (bidId: number): Promise<import('../types').PqFloorResponse> =>
    api.get(`/bids/${bidId}/pq-floor`).then((r) => r.data),
}

export const journalApi = {
  create: (req: import('../types').JournalCreateRequest): Promise<import('../types').JournalOut> =>
    api.post('/journal', req).then((r) => r.data),

  recordResult: (journalId: number, req: import('../types').JournalResultRequest): Promise<import('../types').JournalOut> =>
    api.put(`/journal/${journalId}/result`, req).then((r) => r.data),

  list: (params?: { result?: string; page?: number; size?: number }) =>
    api.get('/journal', { params }).then((r) => r.data as { total: number; items: import('../types').JournalOut[] }),

  stats: (): Promise<import('../types').JournalStats> =>
    api.get('/journal/stats').then((r) => r.data),

  pending: () =>
    api.get('/journal/pending').then((r) => r.data as { count: number; items: Record<string, unknown>[] }),

  gapAnalysis: () =>
    api.get('/journal/gap-analysis').then((r) => r.data as import('../types').JournalGapAnalysis),

  recommendationEffect: (tolerance = 0.003) =>
    api.get('/journal/recommendation-effect', { params: { tolerance } }).then((r) => r.data as import('../types').RecommendationEffect),

  createManual: (req: import('../types').ManualJournalRequest): Promise<import('../types').JournalOut> =>
    api.post('/journal/manual', req).then((r) => r.data),
}

// Phase 2 — 사전규격 API
export const preSpecApi = {
  list: (params?: {
    order_agency?: string
    industry?: string
    days_back?: number
    matched_only?: boolean
    page?: number
    size?: number
  }): Promise<{ items: import('../types').PreSpecNotice[]; total: number; page: number; size: number }> =>
    api.get('/pre-spec/list', { params }).then((r) => r.data),

  summary: (days_back = 30): Promise<import('../types').PreSpecSummary> =>
    api.get('/pre-spec/summary', { params: { days_back } }).then((r) => r.data),
}

// Phase 3 — 계약정보 API
export const contractsApi = {
  list: (params?: {
    agency_name?: string
    days_back?: number
    joint_only?: boolean
    page?: number
    size?: number
  }): Promise<{ items: import('../types').BidContract[]; total: number; page: number; size: number }> =>
    api.get('/contracts/list', { params }).then((r) => r.data),

  summary: (days_back = 90): Promise<import('../types').ContractSummary> =>
    api.get('/contracts/summary', { params: { days_back } }).then((r) => r.data),
}