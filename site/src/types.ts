export type Incident = {
  case_number: string;
  report_datetime: string | null;
  offense_datetime: string | null;
  offenses: string[];
  location_raw: string | null;
  address_raw: string | null;
  apt: string | null;
  city: string | null;
  zip: string | null;
  district_zone: string | null;
  area_command: string | null;
  census_tract: string | null;
  property: { status: string; type: string }[] | null;
  lat: number | null;
  lon: number | null;
  geocode_status: string;
};

export type Meta = {
  last_pulled_at: string | null;
  count: number;
  geocoded_count: number;
  offenses: string[];
  zips: string[];
  zones: string[];
  area_commands: string[];
};

export type Filters = {
  dateFrom: string;
  dateTo: string;
  offenses: string[];
  zips: string[];
  zones: string[];
  areas: string[];
  q: string;
  showUngeocoded: boolean;
};
