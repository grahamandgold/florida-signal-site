import * as entityModule from "@nodable/entities";
import { XMLParser } from "fast-xml-parser";
import { SyntaxValidator } from "fast-xml-validator";

export type Row = Record<string, unknown>;
export type FaaCaseType = "OE" | "NRA";

const CASE_TAG: Record<FaaCaseType, "OECase" | "NRACase"> = {
  OE: "OECase",
  NRA: "NRACase",
};

const OUTPUT_FIELDS = [
  "asn", "case_id", "case_type", "year", "date_entered", "date_completed",
  "expiration_date", "received_date", "status_code", "structure_type",
  "structure_description", "agl_height", "agl_height_det", "amsl_height",
  "sponsor", "sponsor_city", "sponsor_state", "nearest_airport",
  "nearest_city", "nearest_state", "lat", "lon", "raw",
] as const;

// The audited 2026-08-31 OE response contained 1,627 valid predefined and
// numeric XML references. Keep finite document-wide limits with roughly 2.5x
// headroom; the collector separately enforces its raw-response byte ceiling.
export const FAA_MAX_ENTITY_EXPANSIONS = 4_096;
export const FAA_MAX_ENTITY_EXPANDED_LENGTH = 1_000_000;
export const FAA_MAX_NESTED_TAGS = 8;

const ALLOWED_CASE_FIELDS = [
  "aglStructureHeight", "aglStructureHeightDet", "amslOverallHeightProposed",
  "amslOverallHeightDet", "asn", "asnSequence", "caseId", "caseType",
  "createdDate", "dateBuilt", "dateCompleted", "dateEntered",
  "directionFromNearestAirport", "distanceFromNearestAirport",
  "expirationDate", "faaGeographyId", "fccAsrNumber",
  "latLongAccuracy", "latitude", "locatorId", "longitude",
  "nearestAirportName", "nearestCity", "nearestState", "receivedDate",
  "recommendedMarkLightType", "recommendedMarkLightTypeOther",
  "siteElevationProposed", "sponsor", "sponsorCity", "sponsorState",
  "statusCode", "structureDescription", "structureType", "year",
] as const;

const REQUIRED_CASE_FIELDS: Record<FaaCaseType, readonly string[]> = {
  OE: ["caseId", "asn", "caseType", "year", "dateEntered", "latitude", "longitude"],
  NRA: ["caseId", "asn", "caseType", "year", "createdDate", "latitude", "longitude"],
};

const allowedCaseFields = new Set<string>(ALLOWED_CASE_FIELDS);
// @nodable/entities 3.0.0 exposes this named runtime export, while its root
// declaration incorrectly describes the same class as a default export.
// Keep the workaround local and structurally type the API fast-xml-parser uses.
type EntityDecoderInstance = {
  setExternalEntities: (entities: Record<string, string>) => void;
  addInputEntities: (entities: Record<string, unknown>) => void;
  reset: () => void;
  decode: (value: string) => string;
  setXmlVersion: (version: string) => void;
};
const EntityDecoder = (entityModule as unknown as {
  EntityDecoder: new (options?: Record<string, unknown>) => EntityDecoderInstance;
}).EntityDecoder;

function newXmlParser(): XMLParser {
  const entityDecoder = new EntityDecoder({
    numericAllowed: true,
    limit: {
      maxTotalExpansions: FAA_MAX_ENTITY_EXPANSIONS,
      maxExpandedLength: FAA_MAX_ENTITY_EXPANDED_LENGTH,
      applyLimitsTo: "all",
    },
    ncr: { xmlVersion: 1.0, onNCR: "allow", nullNCR: "throw" },
    postCheck: (resolved: string, original: string) => {
      const references = original.match(/&[^;\s<&]+;/g) ?? [];
      const invalid = references.find((reference) =>
        !/^&(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9a-f]+);$/i.test(reference)
      );
      if (invalid) throw new Error("FAA XML contains an undeclared entity");
      return resolved;
    },
    onInputEntity: () => "throw",
    onExternalEntity: () => "throw",
  });
  return new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: "@_",
    parseTagValue: false,
    parseAttributeValue: false,
    trimValues: true,
    processEntities: {
      enabled: true,
      maxEntitySize: 256,
      maxExpansionDepth: 8,
      maxTotalExpansions: FAA_MAX_ENTITY_EXPANSIONS,
      maxExpandedLength: FAA_MAX_ENTITY_EXPANDED_LENGTH,
      maxEntityCount: 16,
    },
    entityDecoder,
    ignoreDeclaration: true,
    ignorePiTags: true,
    maxNestedTags: FAA_MAX_NESTED_TAGS,
    strictReservedNames: true,
    isArray: (tagName) => tagName === "OECase" || tagName === "NRACase",
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function textOrNull(value: unknown): string | null {
  if (value === null || value === undefined || typeof value === "object") return null;
  const text = String(value).trim();
  return text || null;
}

function numberOrNull(value: unknown): number | null {
  const text = textOrNull(value);
  if (text === null) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function integerOrNull(value: unknown): number | null {
  const parsed = numberOrNull(value);
  return parsed !== null && Number.isSafeInteger(parsed) ? parsed : null;
}

function roundedIntegerOrNull(value: unknown): number | null {
  const parsed = numberOrNull(value);
  return parsed === null ? null : Math.round(parsed);
}

function dateOrNull(value: unknown): string | null {
  const text = textOrNull(value);
  if (!text) return null;
  const candidate = text.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(candidate)) return null;
  const parsed = new Date(`${candidate}T00:00:00.000Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === candidate
    ? candidate
    : null;
}

function timestampOrNull(value: unknown): string | null {
  const text = textOrNull(value);
  if (!text) return null;
  const parsed = new Date(text);
  return Number.isFinite(parsed.getTime()) ? parsed.toISOString() : null;
}

function assertXmlContentType(contentType: string | null): void {
  const mediaType = (contentType ?? "").split(";", 1)[0].trim().toLowerCase();
  if (!/^(?:application|text)\/(?:[a-z0-9!#$&^_.+-]+\+)?xml$/.test(mediaType)) {
    throw new Error("FAA response is not an XML media type");
  }
}

function parsedRawCase(value: Record<string, unknown>, caseIndex: number): Record<string, string> {
  const unknown = Object.keys(value).filter((field) => !allowedCaseFields.has(field)).sort();
  if (unknown.length) {
    throw new Error(`FAA case ${caseIndex} schema drift: unknown fields: ${unknown.join(",")}`);
  }
  const raw: Record<string, string> = {};
  for (const [field, fieldValue] of Object.entries(value)) {
    if (fieldValue === null || fieldValue === undefined) {
      raw[field] = "";
    } else if (typeof fieldValue === "object") {
      throw new Error(`FAA case ${caseIndex} field ${field} is not scalar`);
    } else {
      raw[field] = String(fieldValue).trim();
    }
  }
  return raw;
}

function mapCase(
  value: Record<string, unknown>,
  expectedType: FaaCaseType,
  expectedYear: number,
  caseIndex: number,
): Row {
  const raw = parsedRawCase(value, caseIndex);
  const missing = REQUIRED_CASE_FIELDS[expectedType]
    .filter((field) => !Object.hasOwn(raw, field) || !raw[field]);
  if (missing.length) {
    throw new Error(`FAA case ${caseIndex} schema drift: missing fields: ${missing.join(",")}`);
  }
  if (raw.caseType !== expectedType) {
    throw new Error(`FAA case ${caseIndex} type does not match ${expectedType}`);
  }
  const caseId = integerOrNull(raw.caseId);
  if (caseId === null) throw new Error(`FAA case ${caseIndex} has invalid caseId`);
  const year = integerOrNull(raw.year);
  if (year !== expectedYear) throw new Error(`FAA case ${caseIndex} year does not match ${expectedYear}`);
  const entered = dateOrNull(raw.dateEntered ?? raw.createdDate);
  if (entered === null) throw new Error(`FAA case ${caseIndex} has invalid entry date`);
  const lat = numberOrNull(raw.latitude);
  const lon = numberOrNull(raw.longitude);
  if (lat === null || lon === null) throw new Error(`FAA case ${caseIndex} has invalid coordinates`);

  return {
    asn: raw.asn,
    case_id: caseId,
    case_type: raw.caseType,
    year,
    date_entered: entered,
    date_completed: dateOrNull(raw.dateCompleted),
    expiration_date: dateOrNull(raw.expirationDate),
    received_date: timestampOrNull(raw.receivedDate),
    status_code: textOrNull(raw.statusCode),
    structure_type: textOrNull(raw.structureType),
    structure_description: textOrNull(raw.structureDescription),
    agl_height: roundedIntegerOrNull(raw.aglStructureHeight),
    agl_height_det: roundedIntegerOrNull(raw.aglStructureHeightDet),
    amsl_height: roundedIntegerOrNull(raw.amslOverallHeightProposed),
    sponsor: textOrNull(raw.sponsor),
    sponsor_city: textOrNull(raw.sponsorCity),
    sponsor_state: textOrNull(raw.sponsorState),
    nearest_airport: textOrNull(raw.nearestAirportName),
    nearest_city: textOrNull(raw.nearestCity),
    nearest_state: textOrNull(raw.nearestState),
    lat,
    lon,
    raw,
  };
}

export function parseFaaCaseList(
  xml: string,
  expectedType: FaaCaseType,
  expectedYear: number,
  contentType: string | null,
): { rows: Row[]; observed: number; schemaTags: Set<string> } {
  assertXmlContentType(contentType);
  if (/<!DOCTYPE\b/i.test(xml)) throw new Error("FAA XML DOCTYPE is not allowed");
  try {
    new SyntaxValidator({
      allowBooleanAttributes: false,
      unpairedTags: [],
      invalidCharSequence: { comment: true, tagValue: true, attrLt: true },
      multipleRoots: false,
    }).validate(xml);
  } catch (error) {
    const details = error as { code?: unknown; line?: unknown; col?: unknown };
    const code = typeof details.code === "string" ? details.code : "InvalidXml";
    const line = typeof details.line === "number" && Number.isInteger(details.line) ? details.line : "?";
    const col = typeof details.col === "number" && Number.isInteger(details.col) ? details.col : "?";
    throw new Error(`FAA XML is malformed: ${code} at ${line}:${col}`);
  }

  const parsed = newXmlParser().parse(xml) as unknown;
  if (!isRecord(parsed) || Object.keys(parsed).length !== 1 || !Object.hasOwn(parsed, "caseList")) {
    throw new Error("FAA XML root must be caseList");
  }
  const envelope = parsed.caseList;
  const caseTag = CASE_TAG[expectedType];
  const schemaTags = new Set<string>(["envelope:caseList", `expected-case:${caseTag}`]);
  if (envelope === "" || (isRecord(envelope) && Object.keys(envelope).length === 0)) {
    return { rows: [], observed: 0, schemaTags };
  }
  if (!isRecord(envelope)) throw new Error("FAA caseList envelope is invalid");
  const unknownEnvelopeFields = Object.keys(envelope).filter((field) => field !== caseTag).sort();
  if (unknownEnvelopeFields.length) {
    throw new Error(`FAA caseList schema drift: unknown fields: ${unknownEnvelopeFields.join(",")}`);
  }
  const cases = envelope[caseTag];
  if (!Array.isArray(cases)) throw new Error(`FAA caseList is missing ${caseTag} records`);
  const rows = cases.map((value, index) => {
    if (!isRecord(value)) throw new Error(`FAA case ${index + 1} is not an object`);
    for (const field of Object.keys(value)) schemaTags.add(`field:${expectedType}:${field}`);
    return mapCase(value, expectedType, expectedYear, index + 1);
  });
  return { rows, observed: cases.length, schemaTags };
}

export function faaContractShape(): string[] {
  return [...OUTPUT_FIELDS].sort();
}

export function faaSourceContract(): Record<string, unknown> {
  return Object.fromEntries((["OE", "NRA"] as FaaCaseType[]).map((type) => [type, {
    case_tag: CASE_TAG[type],
    required_fields: [...REQUIRED_CASE_FIELDS[type]].sort(),
    allowed_fields: [...ALLOWED_CASE_FIELDS].sort(),
  }]));
}
