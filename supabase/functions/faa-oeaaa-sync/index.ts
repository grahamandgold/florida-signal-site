import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  faaContractShape,
  faaSourceContract,
  parseFaaCaseList,
  type FaaCaseType,
  type Row,
} from "./parser.ts";

// Configure this through Supabase Edge Function secrets before deployment.
const SYNC_KEY = Deno.env.get("FL_SIGNAL_SYNC_KEY")?.trim();
const REJECTED_SYNC_KEY_PLACEHOLDER = "__FL_SIGNAL_SYNC_KEY_INJECT_AT_DEPLOY__";
const SOURCE_ID = "faa_oeaaa";
const BUCKET = "fl-signal-source-evidence";
const BASE = "https://oeaaa.faa.gov/oeaaa/services";
const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SRK = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const COLLECTOR_VERSION = "faa-edge-v3-atomic-receipts";
const PARSER_VERSION = "faa-xml-v3-validated-envelope";
const NORMALIZER_VERSION = "faa-row-v3-official-caseid";
const SYNC_KEY_HEADER = "x-florida-signal-sync-key";
const MAX_LOOKBACK_DAYS = 370;
const MAX_YEAR_REQUESTS = 2;
const MAX_RAW_RESPONSE_BYTES = 25_000_000;
const MAX_TOTAL_RAW_BYTES = 100_000_000;
const authHeaders = { apikey: SRK, Authorization: `Bearer ${SRK}` };

type RawObject = Record<string, unknown>;

const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status,
  headers: { "Content-Type": "application/json" },
});
const safeError = (error: unknown) => String(error instanceof Error ? error.message : error).slice(0, 500);

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function ensureBucket(): Promise<void> {
  const found = await fetch(`${SB_URL}/storage/v1/bucket/${BUCKET}`, { headers: authHeaders });
  if (found.ok) {
    if ((await found.json()).public === true) throw new Error("raw-evidence bucket is public");
    return;
  }
  const lookupError = await found.text();
  if (found.status !== 404 && !/not found/i.test(lookupError)) {
    throw new Error(`bucket lookup HTTP ${found.status}: ${lookupError.slice(0, 200)}`);
  }
  const created = await fetch(`${SB_URL}/storage/v1/bucket`, {
    method: "POST",
    headers: { ...authHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({
      id: BUCKET,
      name: BUCKET,
      public: false,
      file_size_limit: 52_428_800,
      allowed_mime_types: ["application/json", "application/xml", "text/xml"],
    }),
  });
  if (!created.ok) {
    const checked = await fetch(`${SB_URL}/storage/v1/bucket/${BUCKET}`, { headers: authHeaders });
    if (!checked.ok || (await checked.json()).public === true) {
      throw new Error(`bucket create HTTP ${created.status}: ${(await created.text()).slice(0, 200)}`);
    }
  }
}

async function upload(key: string, body: string, contentType: string): Promise<void> {
  const encoded = key.split("/").map(encodeURIComponent).join("/");
  const saved = await fetch(`${SB_URL}/storage/v1/object/${BUCKET}/${encoded}`, {
    method: "POST",
    headers: {
      ...authHeaders,
      "Content-Type": contentType,
      "cache-control": "31536000, immutable",
      "x-upsert": "false",
    },
    body,
  });
  if (!saved.ok) throw new Error(`evidence upload HTTP ${saved.status}: ${(await saved.text()).slice(0, 200)}`);
}

async function stage(runId: string, rows: Map<string, Row>): Promise<void> {
  const entries = [...rows.entries()];
  for (let offset = 0; offset < entries.length; offset += 250) {
    const body = entries.slice(offset, offset + 250).map(([row_key, row_data]) => ({
      source_id: SOURCE_ID,
      run_id: runId,
      row_key,
      row_data,
    }));
    const saved = await fetch(
      `${SB_URL}/rest/v1/external_source_run_stage?on_conflict=source_id,run_id,row_key`,
      {
        method: "POST",
        headers: {
          ...authHeaders,
          "Content-Type": "application/json",
          Prefer: "resolution=merge-duplicates,return=minimal",
        },
        body: JSON.stringify(body),
      },
    );
    if (!saved.ok) throw new Error(`stage HTTP ${saved.status}: ${(await saved.text()).slice(0, 300)}`);
  }
}

async function commit(runId: string, receipt: Row, manifest: Row): Promise<Row> {
  const committed = await fetch(`${SB_URL}/rest/v1/rpc/fs_commit_external_source_run`, {
    method: "POST",
    headers: { ...authHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({
      p_source_id: SOURCE_ID,
      p_run_id: runId,
      p_receipt: receipt,
      p_manifest: manifest,
    }),
  });
  if (!committed.ok) throw new Error(`commit HTTP ${committed.status}: ${(await committed.text()).slice(0, 500)}`);
  return await committed.json();
}

function laterClock(current: string | null, ...dates: Array<string | null>): string | null {
  for (const date of dates) {
    if (!date) continue;
    const parsed = new Date(date.length === 10 ? `${date}T00:00:00.000Z` : date);
    if (!Number.isFinite(parsed.getTime())) continue;
    const iso = parsed.toISOString();
    if (!current || iso > current) current = iso;
  }
  return current;
}

Deno.serve(async (request: Request) => {
  if (!SYNC_KEY || SYNC_KEY === REJECTED_SYNC_KEY_PLACEHOLDER) {
    return response({ error: "collector authentication is not configured" }, 503);
  }
  if (request.headers.get(SYNC_KEY_HEADER)?.trim() !== SYNC_KEY) {
    return response({ error: "unauthorized" }, 401);
  }
  const url = new URL(request.url);
  const today = new Date().toISOString().slice(0, 10);
  const since = url.searchParams.get("since") ?? new Date(Date.now() - 60 * 86_400_000).toISOString().slice(0, 10);
  const sinceDate = new Date(`${since}T00:00:00.000Z`);
  const todayDate = new Date(`${today}T00:00:00.000Z`);
  const lookbackDays = Math.floor((todayDate.getTime() - sinceDate.getTime()) / 86_400_000);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(since)
    || !Number.isFinite(sinceDate.getTime())
    || sinceDate.toISOString().slice(0, 10) !== since
    || lookbackDays < 0
    || lookbackDays > MAX_LOOKBACK_DAYS
  ) {
    return response({ error: `since must be a real date within ${MAX_LOOKBACK_DAYS} days` }, 400);
  }
  const types = [...new Set((url.searchParams.get("types") ?? "OE,NRA").split(","))];
  if (!types.length || types.some((type) => !["OE", "NRA"].includes(type))) {
    return response({ error: "types must be a subset of OE,NRA" }, 400);
  }

  const runId = crypto.randomUUID();
  const startedAt = new Date().toISOString();
  const rows = new Map<string, Row>();
  const rawObjects: RawObject[] = [];
  const schemaTags = new Set<string>();
  const outcomes: Row[] = [];
  let pagesAttempted = 0;
  let pagesSucceeded = 0;
  let responsesObserved = 0;
  let rowsObserved = 0;
  let totalRawBytes = 0;
  let observedAt = startedAt;
  let eventThrough: string | null = null;

  try {
    await ensureBucket();
    const firstYear = Number(since.slice(0, 4));
    const lastYear = Number(today.slice(0, 4));
    if (lastYear - firstYear + 1 > MAX_YEAR_REQUESTS) {
      throw new Error(`request spans more than ${MAX_YEAR_REQUESTS} calendar years`);
    }
    for (const type of types as FaaCaseType[]) {
      let typeAccepted = 0;
      for (let year = firstYear; year <= lastYear; year += 1) {
        pagesAttempted += 1;
        const query = new URLSearchParams({ state: "FL", dateEnteredStart: since, dateEnteredEnd: today });
        const source = await fetch(`${BASE}/caseList/${type}/${year}?${query}`);
        observedAt = new Date().toISOString();
        responsesObserved += 1;
        const rawXml = await source.text();
        const rawBytes = new TextEncoder().encode(rawXml).byteLength;
        if (rawBytes > MAX_RAW_RESPONSE_BYTES) {
          throw new Error(`${type}/${year} response exceeds ${MAX_RAW_RESPONSE_BYTES} bytes`);
        }
        totalRawBytes += rawBytes;
        if (totalRawBytes > MAX_TOTAL_RAW_BYTES) {
          throw new Error(`run exceeds ${MAX_TOTAL_RAW_BYTES} raw response bytes`);
        }
        const key = `${SOURCE_ID}/${runId}/${type.toLowerCase()}-${year}.xml`;
        await upload(key, rawXml, "application/xml");
        rawObjects.push({
          key,
          sha256: await sha256(rawXml),
          bytes: rawBytes,
          content_type: "application/xml",
          source_path: `${BASE}/caseList/${type}/${year}`,
          observed_at: observedAt,
          http_status: source.status,
          source_content_type: source.headers.get("content-type"),
        });
        if (!source.ok) throw new Error(`${type}/${year} HTTP ${source.status}`);
        const parsed = parseFaaCaseList(rawXml, type, year, source.headers.get("content-type"));
        for (const schemaTag of parsed.schemaTags) schemaTags.add(schemaTag);
        rowsObserved += parsed.observed;
        for (const row of parsed.rows) {
          rows.set(String(row.asn), row);
          typeAccepted += 1;
          eventThrough = laterClock(eventThrough, row.received_date as string | null, row.date_entered as string | null);
        }
        pagesSucceeded += 1;
      }
      outcomes.push({ type, accepted_before_global_dedupe: typeAccepted });
    }

    const rowsRejected = rowsObserved - rows.size;
    const status = rowsRejected > 0 ? "partial" : rows.size ? "ok" : "empty";
    if (rows.size) await stage(runId, rows);
    const sourceSchemaSha = await sha256(JSON.stringify([...schemaTags].sort()));
    const contractSha = await sha256(JSON.stringify({
      source_id: SOURCE_ID,
      parser: PARSER_VERSION,
      key: ["asn"],
      fields: faaContractShape(),
      source_contract: faaSourceContract(),
    }));
    const completedAt = new Date().toISOString();
    const manifestKey = `${SOURCE_ID}/${runId}/manifest.json`;
    const manifest: Row = {
      manifest_version: 1,
      source_id: SOURCE_ID,
      run_id: runId,
      started_at: startedAt,
      observed_at: observedAt,
      completed_at: completedAt,
      request: { state: "FL", types, since, through: today },
      raw_objects: rawObjects,
      pages_attempted: pagesAttempted,
      pages_succeeded: pagesSucceeded,
      responses_observed: responsesObserved,
      rows_observed: rowsObserved,
      rows_staged: rows.size,
      rows_rejected: rowsRejected,
      outcomes,
    };
    await upload(manifestKey, JSON.stringify(manifest), "application/json");
    const receipt = await commit(runId, {
      collector_name: "faa-oeaaa-sync",
      collector_version: COLLECTOR_VERSION,
      parser_version: PARSER_VERSION,
      normalizer_version: NORMALIZER_VERSION,
      status,
      reason_code: rowsRejected ? "row_contract_rejections" : null,
      reason_detail: rowsRejected ? "source cases without a unique admissible ASN were not committed" : null,
      started_at: startedAt,
      observed_at: observedAt,
      completed_at: completedAt,
      attempted_event_from: `${since}T00:00:00.000Z`,
      attempted_event_through: `${today}T23:59:59.999Z`,
      event_through: eventThrough,
      pages_attempted: pagesAttempted,
      pages_succeeded: pagesSucceeded,
      responses_observed: responsesObserved,
      rows_observed: rowsObserved,
      rows_rejected: rowsRejected,
      schema_contract_sha256: contractSha,
      source_schema_sha256: sourceSchemaSha,
      raw_manifest_object_key: manifestKey,
      outcomes,
      source_metadata: { state: "FL", types, since, through: today },
    }, manifest);
    return response({ ok: status === "ok" || status === "empty", receipt });
  } catch (error) {
    const terminalAt = new Date().toISOString();
    const failureKey = `${SOURCE_ID}/${runId}/failure-manifest.json`;
    try {
      await ensureBucket();
      const manifest: Row = {
        manifest_version: 1,
        source_id: SOURCE_ID,
        run_id: runId,
        started_at: startedAt,
        observed_at: terminalAt,
        completed_at: terminalAt,
        request: { state: "FL", types, since, through: today },
        raw_objects: rawObjects,
        pages_attempted: pagesAttempted,
        pages_succeeded: pagesSucceeded,
        responses_observed: responsesObserved,
        rows_observed: rowsObserved,
        rows_staged_before_failure: rows.size,
        outcomes,
        error_class: error instanceof Error ? error.name : "Error",
        error: safeError(error),
      };
      await upload(failureKey, JSON.stringify(manifest), "application/json");
      const contractSha = await sha256(JSON.stringify({
        source_id: SOURCE_ID,
        parser: PARSER_VERSION,
        key: ["asn"],
        fields: faaContractShape(),
        source_contract: faaSourceContract(),
      }));
      const receipt = await commit(runId, {
        collector_name: "faa-oeaaa-sync",
        collector_version: COLLECTOR_VERSION,
        parser_version: PARSER_VERSION,
        normalizer_version: NORMALIZER_VERSION,
        status: "failed",
        reason_code: "collector_exception",
        reason_detail: safeError(error),
        started_at: startedAt,
        observed_at: terminalAt,
        completed_at: terminalAt,
        attempted_event_from: `${since}T00:00:00.000Z`,
        attempted_event_through: `${today}T23:59:59.999Z`,
        event_through: null,
        pages_attempted: pagesAttempted,
        pages_succeeded: pagesSucceeded,
        responses_observed: responsesObserved,
        rows_observed: rowsObserved,
        rows_rejected: rowsObserved,
        schema_contract_sha256: contractSha,
        source_schema_sha256: null,
        raw_manifest_object_key: failureKey,
        outcomes,
        source_metadata: { state: "FL", types, since, through: today },
      }, manifest);
      return response({ ok: false, error: safeError(error), receipt }, 500);
    } catch (receiptError) {
      return response({ ok: false, error: safeError(error), receipt_error: safeError(receiptError), run_id: runId }, 500);
    }
  }
});
