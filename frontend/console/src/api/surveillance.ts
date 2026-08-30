import { api } from "../api";
import type {
  SurveillanceAlert,
  SurveillanceAlertPage,
  SurveillanceTask,
  SurveillanceTaskPage,
  Watchlist,
  WatchlistMember,
  WatchlistMemberPage,
  WatchlistPage,
} from "../types";

export function listWatchlists(
  offset = 0,
  limit = 100,
): Promise<WatchlistPage> {
  return api<WatchlistPage>(
    `/api/v1/surveillance/watchlists?offset=${offset}&limit=${limit}`,
  );
}

export function createWatchlist(
  body: Record<string, unknown>,
): Promise<Watchlist> {
  return api<Watchlist>("/api/v1/surveillance/watchlists", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateWatchlist(
  watchlistId: string,
  body: Record<string, unknown>,
): Promise<Watchlist> {
  return api<Watchlist>(
    `/api/v1/surveillance/watchlists/${encodeURIComponent(watchlistId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}

export function listMembers(
  watchlistId: string,
  offset = 0,
  limit = 100,
): Promise<WatchlistMemberPage> {
  return api<WatchlistMemberPage>(
    `/api/v1/surveillance/watchlists/${encodeURIComponent(watchlistId)}/members?offset=${offset}&limit=${limit}`,
  );
}

export function createMember(
  watchlistId: string,
  body: Record<string, unknown>,
): Promise<WatchlistMember> {
  return api<WatchlistMember>(
    `/api/v1/surveillance/watchlists/${encodeURIComponent(watchlistId)}/members`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function listTasks(
  offset = 0,
  limit = 100,
): Promise<SurveillanceTaskPage> {
  return api<SurveillanceTaskPage>(
    `/api/v1/surveillance/tasks?offset=${offset}&limit=${limit}`,
  );
}

export function createTask(
  body: Record<string, unknown>,
): Promise<SurveillanceTask> {
  return api<SurveillanceTask>("/api/v1/surveillance/tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function taskAction(
  taskId: string,
  action: "start" | "pause" | "resume",
): Promise<SurveillanceTask> {
  return api<SurveillanceTask>(
    `/api/v1/surveillance/tasks/${encodeURIComponent(taskId)}/${action}`,
    { method: "POST" },
  );
}

export function listAlerts(query = ""): Promise<SurveillanceAlertPage> {
  return api<SurveillanceAlertPage>(
    `/api/v1/surveillance/alerts${query ? `?${query}` : ""}`,
  );
}

export function triageAlert(
  alertId: string,
  body: Record<string, unknown>,
): Promise<SurveillanceAlert> {
  return api<SurveillanceAlert>(
    `/api/v1/surveillance/alerts/${encodeURIComponent(alertId)}/status`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}

export function createAlertFeedback(
  alertId: string,
): Promise<Record<string, unknown>> {
  return api<Record<string, unknown>>(
    `/api/v1/surveillance/alerts/${encodeURIComponent(alertId)}/feedback`,
    { method: "POST", body: JSON.stringify({ correction: {} }) },
  );
}
