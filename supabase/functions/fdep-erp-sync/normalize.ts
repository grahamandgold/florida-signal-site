export type Row = Record<string, unknown>;

export const DEFAULT_LOOKBACK_DAYS = 90;
export const MAX_LOOKBACK_DAYS = 370;

const OUTPUT_FIELDS = [
  "layer_id", "objectid", "permit_id", "application_id", "project_id",
  "project_name", "applicant_name", "applicant_company", "permit_type",
  "permit_status", "defined_status", "division", "permitting_program",
  "district", "office_abbrev", "location_id", "location_name",
  "street_address", "city", "state", "zip5", "zip4", "received_date",
  "agency_action", "agency_action_date", "documents_url", "lat", "lon",
  "raw",
] as const;

const REQUIRED_SOURCE_FIELDS: Record<number, readonly string[]> = {
  0: [
    "OBJECTID", "COE_NUMBER", "APPLICATION_NUMBER", "PROJECT_NAME",
    "APPLICANT_NAME", "APPLICANT_COMPANY", "PERMIT_TYPE_ABBREV",
    "PERMIT_TYPE_DESCRIPTION", "DISTRICT", "OFFICE_ABBREV", "SITE_NAME",
    "SITE_ADDRESS_1", "SITE_ADDRESS_2", "SITE_CITY", "SITE_STATE",
    "SITE_ZIP5", "SITE_ZIP4", "RECEIVE_DATE", "AGENCY_ACTION",
    "AGENCY_ACTION_DATE", "DEP_SPGP_STATUS", "COE_SPGP_STATUS", "DOCUMENTS",
  ],
  1: [
    "OBJECTID", "PERMIT_ID", "APPLICATION_ID", "PROJECT_ID", "PROJECT_NAME",
    "APPLICANT_NAME", "APPLICANT_COMPANY", "PERMIT_TYPE", "PERMIT_STATUS",
    "DEFINED_STATUS", "DIVISION", "PERMITTING_PROGRAM", "DISTRICT",
    "OFFICE_ABBREV", "LOCATION_ID", "LOCATION_NAME", "STREET_ADDRESS",
    "CITY", "STATE", "ZIP5", "ZIP4", "RECEIVED_DATE", "AGENCY_ACTION",
    "AGENCY_ACTION_DATE", "DOCUMENTS",
  ],
};

function numberOrNull(value: unknown): number | null {
  const parsed = value === null || value === undefined || value === "" ? NaN : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function integerOrNull(value: unknown): number | null {
  const parsed = numberOrNull(value);
  return parsed === null ? null : Math.trunc(parsed);
}

function textOrNull(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function joinedText(...values: unknown[]): string | null {
  const parts = values.map(textOrNull).filter((value): value is string => value !== null);
  return parts.length ? parts.join(" ") : null;
}

function fixedWidthNumber(value: unknown, width: number): string | null {
  const integer = integerOrNull(value);
  return integer === null || integer < 0 ? textOrNull(value) : String(integer).padStart(width, "0");
}

function esriDate(value: unknown): string | null {
  const parsed = numberOrNull(value);
  if (parsed === null) return null;
  const date = new Date(parsed);
  return Number.isFinite(date.getTime()) ? date.toISOString().slice(0, 10) : null;
}

function baseRow(layer: number, objectid: number, attributes: Row, geometry: Row): Row {
  return {
    layer_id: layer,
    objectid,
    permit_id: null,
    application_id: null,
    project_id: null,
    project_name: null,
    applicant_name: null,
    applicant_company: null,
    permit_type: null,
    permit_status: null,
    defined_status: null,
    division: null,
    permitting_program: null,
    district: null,
    office_abbrev: null,
    location_id: null,
    location_name: null,
    street_address: null,
    city: null,
    state: null,
    zip5: null,
    zip4: null,
    received_date: null,
    agency_action: null,
    agency_action_date: null,
    documents_url: null,
    lat: numberOrNull(geometry.y),
    lon: numberOrNull(geometry.x),
    raw: attributes,
  };
}

export function mapFeature(layer: number, feature: Row): Row | null {
  const attributes = (feature.attributes ?? {}) as Row;
  const geometry = (feature.geometry ?? {}) as Row;
  const objectid = integerOrNull(attributes.OBJECTID);
  if (objectid === null) return null;
  const row = baseRow(layer, objectid, attributes, geometry);

  if (layer === 0) {
    return {
      ...row,
      permit_id: textOrNull(attributes.COE_NUMBER),
      application_id: textOrNull(attributes.APPLICATION_NUMBER),
      project_name: textOrNull(attributes.PROJECT_NAME),
      applicant_name: textOrNull(attributes.APPLICANT_NAME),
      applicant_company: textOrNull(attributes.APPLICANT_COMPANY),
      permit_type: textOrNull(attributes.PERMIT_TYPE_DESCRIPTION)
        ?? textOrNull(attributes.PERMIT_TYPE_ABBREV),
      permit_status: textOrNull(attributes.DEP_SPGP_STATUS),
      defined_status: textOrNull(attributes.COE_SPGP_STATUS),
      permitting_program: "ERP SPGP",
      district: textOrNull(attributes.DISTRICT),
      office_abbrev: textOrNull(attributes.OFFICE_ABBREV),
      location_name: textOrNull(attributes.SITE_NAME),
      street_address: joinedText(attributes.SITE_ADDRESS_1, attributes.SITE_ADDRESS_2),
      city: textOrNull(attributes.SITE_CITY),
      state: textOrNull(attributes.SITE_STATE),
      zip5: fixedWidthNumber(attributes.SITE_ZIP5, 5),
      zip4: fixedWidthNumber(attributes.SITE_ZIP4, 4),
      received_date: esriDate(attributes.RECEIVE_DATE),
      agency_action: textOrNull(attributes.AGENCY_ACTION),
      agency_action_date: esriDate(attributes.AGENCY_ACTION_DATE),
      documents_url: textOrNull(attributes.DOCUMENTS),
    };
  }

  if (layer === 1) {
    return {
      ...row,
      permit_id: textOrNull(attributes.PERMIT_ID),
      application_id: textOrNull(attributes.APPLICATION_ID),
      project_id: integerOrNull(attributes.PROJECT_ID),
      project_name: textOrNull(attributes.PROJECT_NAME),
      applicant_name: textOrNull(attributes.APPLICANT_NAME),
      applicant_company: textOrNull(attributes.APPLICANT_COMPANY),
      permit_type: textOrNull(attributes.PERMIT_TYPE),
      permit_status: textOrNull(attributes.PERMIT_STATUS),
      defined_status: textOrNull(attributes.DEFINED_STATUS),
      division: textOrNull(attributes.DIVISION),
      permitting_program: textOrNull(attributes.PERMITTING_PROGRAM),
      district: textOrNull(attributes.DISTRICT),
      office_abbrev: textOrNull(attributes.OFFICE_ABBREV),
      location_id: textOrNull(attributes.LOCATION_ID),
      location_name: textOrNull(attributes.LOCATION_NAME),
      street_address: textOrNull(attributes.STREET_ADDRESS),
      city: textOrNull(attributes.CITY),
      state: textOrNull(attributes.STATE),
      zip5: fixedWidthNumber(attributes.ZIP5, 5),
      zip4: fixedWidthNumber(attributes.ZIP4, 4),
      received_date: esriDate(attributes.RECEIVED_DATE),
      agency_action: textOrNull(attributes.AGENCY_ACTION),
      agency_action_date: esriDate(attributes.AGENCY_ACTION_DATE),
      documents_url: textOrNull(attributes.DOCUMENTS),
    };
  }

  throw new Error(`unsupported FDEP layer ${layer}`);
}

export function assertLayerSchema(layer: number, payload: Row): void {
  const required = REQUIRED_SOURCE_FIELDS[layer];
  if (!required) throw new Error(`unsupported FDEP layer ${layer}`);
  const fields = Array.isArray(payload.fields)
    ? new Set(payload.fields.map((field) => textOrNull((field as Row)?.name)).filter(Boolean))
    : new Set<string>();
  const missing = required.filter((name) => !fields.has(name));
  if (missing.length) throw new Error(`layer ${layer} source schema missing: ${missing.join(",")}`);
}

export function contractShape(): string[] {
  return [...OUTPUT_FIELDS].sort();
}

export function layerReceivedDateField(layer: number): "RECEIVE_DATE" | "RECEIVED_DATE" {
  if (layer === 0) return "RECEIVE_DATE";
  if (layer === 1) return "RECEIVED_DATE";
  throw new Error(`unsupported FDEP layer ${layer}`);
}

export function layerDateWhere(layer: number, since: string, through: string): string {
  const field = layerReceivedDateField(layer);
  const throughDate = new Date(`${through}T00:00:00.000Z`);
  if (!Number.isFinite(throughDate.getTime()) || throughDate.toISOString().slice(0, 10) !== through) {
    throw new Error("through must be a real YYYY-MM-DD date");
  }
  const untilExclusive = new Date(throughDate.getTime() + 86_400_000).toISOString().slice(0, 10);
  return `${field} >= DATE '${since}' AND ${field} < DATE '${untilExclusive}'`;
}

export function resolveSince(
  requested: string | null,
  now: Date = new Date(),
): { since: string; sinceMode: "explicit" | "default_90_day_lookback"; through: string } {
  const through = now.toISOString().slice(0, 10);
  const since = requested
    ?? new Date(now.getTime() - DEFAULT_LOOKBACK_DAYS * 86_400_000).toISOString().slice(0, 10);
  const sinceDate = new Date(`${since}T00:00:00.000Z`);
  const throughDate = new Date(`${through}T00:00:00.000Z`);
  const lookbackDays = Math.floor((throughDate.getTime() - sinceDate.getTime()) / 86_400_000);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(since)
    || !Number.isFinite(sinceDate.getTime())
    || sinceDate.toISOString().slice(0, 10) !== since
    || lookbackDays < 0
    || lookbackDays > MAX_LOOKBACK_DAYS
  ) {
    throw new Error(`since must be a real date within ${MAX_LOOKBACK_DAYS} days`);
  }
  return {
    since,
    sinceMode: requested === null ? "default_90_day_lookback" : "explicit",
    through,
  };
}

export function layerSourceContract(): Record<string, string[]> {
  return Object.fromEntries(
    Object.entries(REQUIRED_SOURCE_FIELDS).map(([layer, fields]) => [layer, [...fields].sort()]),
  );
}
