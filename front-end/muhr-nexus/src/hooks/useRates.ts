import { useQuery } from "@tanstack/react-query";
import { API_CONFIG } from "@/config/api";
import { getRates } from "@/lib/muhrApi";
import type { Rates } from "@/lib/pkr";

const TEN_MINUTES = 10 * 60 * 1000;

/** BTC/PKR from the registry: fetched on load, then every ten minutes. */
export function useRates(): { rates: Rates | null; stale: boolean; fetchedAt: string | null } {
  const q = useQuery({
    queryKey: [API_CONFIG.BASE_URL, "rates"],
    queryFn: getRates,
    staleTime: TEN_MINUTES,
    refetchInterval: TEN_MINUTES,
    retry: 2,
  });
  const rates = q.data ?? null;
  return { rates, stale: rates ? rates.stale || q.isError : false, fetchedAt: rates?.fetched_at ?? null };
}
