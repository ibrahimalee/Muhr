import { useQuery } from "@tanstack/react-query";
import { getBuyerWallet, getHealth, getJobs, getSellers, getStats } from "@/lib/muhrApi";
import { API_CONFIG } from "@/config/api";

const qk = {
  health: [API_CONFIG.BASE_URL, "health"] as const,
  sellers: [API_CONFIG.BASE_URL, "sellers"] as const,
  stats: [API_CONFIG.BASE_URL, "stats"] as const,
  jobs: (limit: number) => [API_CONFIG.BASE_URL, "jobs", limit] as const,
  buyerWallet: [API_CONFIG.BASE_URL, "buyer-wallet"] as const,
};

/**
 * Polling + cache for core registry data used on the MUHR Nexus home surface.
 */
export function useMuhrRegistry(options?: { jobsLimit?: number }) {
  const lim = options?.jobsLimit ?? 100;

  const health = useQuery({ queryKey: qk.health, queryFn: getHealth, refetchInterval: 15_000, retry: 3 });
  const sellers = useQuery({ queryKey: qk.sellers, queryFn: getSellers, refetchInterval: 12_000, retry: 3 });
  const stats = useQuery({ queryKey: qk.stats, queryFn: getStats, refetchInterval: 12_000, retry: 3 });
  const jobs = useQuery({ queryKey: qk.jobs(lim), queryFn: () => getJobs(lim), refetchInterval: 15_000, retry: 3 });
  const buyerWallet = useQuery({
    queryKey: qk.buyerWallet,
    queryFn: getBuyerWallet,
    refetchInterval: 20_000,
    retry: 1,
  });

  const anyError = health.error || sellers.error || stats.error || jobs.error;
  const isLoading = health.isPending || sellers.isPending || stats.isPending || jobs.isPending;

  return {
    health: health.data,
    demoMode: stats.data?.demo_mode,
    sellers: sellers.data?.sellers,
    stats: stats.data,
    jobs: jobs.data?.jobs,
    jobsTotal: jobs.data?.total,
    buyerWallet: buyerWallet.data,
    isLoading,
    hasError: Boolean(anyError),
    refetch: () => {
      void health.refetch();
      void sellers.refetch();
      void stats.refetch();
      void jobs.refetch();
      void buyerWallet.refetch();
    },
  };
}
