-- Move 17 GloFAS stations to the centre of their river cell, as in the seed data (AB#45972).
-- 13 lay on a cell boundary next to a much smaller stream: coordinates only, their thresholds already belong to the river cell.
-- 4 lay in a small cell next to the river (G5142, G1966, G1967, G5368): coordinates and the v4 thresholds of GloFAS's own river cell.
-- On a database without these stations, nothing changes; seed-init then loads them from the seed data.

UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(40.975, 11.675), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ETH' AND "layerName" = 'glofasStations' AND "referenceId" = 'G1045';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(34.575, 8.225), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ETH' AND "layerName" = 'glofasStations' AND "referenceId" = 'G1603';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(41.675, 11.075), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ETH' AND "layerName" = 'glofasStations' AND "referenceId" = 'G4954';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(35.725, 10.025), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ETH' AND "layerName" = 'glofasStations' AND "referenceId" = 'G4979';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(38.625, 8.675), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ETH' AND "layerName" = 'glofasStations' AND "referenceId" = 'G5068';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(41.975, 4.325), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ETH' AND "layerName" = 'glofasStations' AND "referenceId" = 'G5141';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(37.475, 2.825), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ETH' AND "layerName" = 'glofasStations' AND "referenceId" = 'G5173';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(37.775, 8.225), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ETH' AND "layerName" = 'glofasStations' AND "referenceId" = 'G6108';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(37.225, -1.075), 4326), "attributes" = jsonb_set("attributes", '{thresholds}', '[{"return_period": 1.5, "threshold_value": 193.9387707781156}, {"return_period": 2.0, "threshold_value": 268.61727790565294}, {"return_period": 5.0, "threshold_value": 452.3989865536744}, {"return_period": 10.0, "threshold_value": 574.0784690527867}, {"return_period": 20.0, "threshold_value": 690.7963500137164}, {"return_period": 50.0, "threshold_value": 841.875674672389}, {"return_period": 100.0, "threshold_value": 955.0883684281275}, {"return_period": 200.0, "threshold_value": 1067.8879680814985}, {"return_period": 500.0, "threshold_value": 1216.7056208983972}]'::jsonb), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'KEN' AND "layerName" = 'glofasStations' AND "referenceId" = 'G5142';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(40.075, -1.525), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'KEN' AND "layerName" = 'glofasStations' AND "referenceId" = 'G5305';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(120.725, 14.925), 4326), "attributes" = jsonb_set("attributes", '{thresholds}', '[{"return_period": 1.5, "threshold_value": 2244.8860224455666}, {"return_period": 2.0, "threshold_value": 2598.7096992563374}, {"return_period": 5.0, "threshold_value": 3469.459830527114}, {"return_period": 10.0, "threshold_value": 4045.9721838972855}, {"return_period": 20.0, "threshold_value": 4598.976674474867}, {"return_period": 50.0, "threshold_value": 5314.784263524918}, {"return_period": 100.0, "threshold_value": 5851.1813221578195}, {"return_period": 200.0, "threshold_value": 6385.621158026225}, {"return_period": 500.0, "threshold_value": 7090.713039470754}]'::jsonb), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'PHL' AND "layerName" = 'glofasStations' AND "referenceId" = 'G1966';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(120.475, 15.375), 4326), "attributes" = jsonb_set("attributes", '{thresholds}', '[{"return_period": 1.5, "threshold_value": 93.50843271922624}, {"return_period": 2.0, "threshold_value": 106.95792826244126}, {"return_period": 5.0, "threshold_value": 140.0567590567509}, {"return_period": 10.0, "threshold_value": 161.97106506688084}, {"return_period": 20.0, "threshold_value": 182.99179352248046}, {"return_period": 50.0, "threshold_value": 210.20097032349184}, {"return_period": 100.0, "threshold_value": 230.59041942566466}, {"return_period": 200.0, "threshold_value": 250.90547085302546}, {"return_period": 500.0, "threshold_value": 277.70732369261646}]'::jsonb), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'PHL' AND "layerName" = 'glofasStations' AND "referenceId" = 'G1967';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(125.575, 8.875), 4326), "attributes" = jsonb_set("attributes", '{thresholds}', '[{"return_period": 1.5, "threshold_value": 2577.0694564072737}, {"return_period": 2.0, "threshold_value": 3193.3427102679025}, {"return_period": 5.0, "threshold_value": 4709.973879596918}, {"return_period": 10.0, "threshold_value": 5714.115680125144}, {"return_period": 20.0, "threshold_value": 6677.312603179137}, {"return_period": 50.0, "threshold_value": 7924.07222090232}, {"return_period": 100.0, "threshold_value": 8858.343108776677}, {"return_period": 200.0, "threshold_value": 9789.204999117354}, {"return_period": 500.0, "threshold_value": 11017.300506928505}]'::jsonb), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'PHL' AND "layerName" = 'glofasStations' AND "referenceId" = 'G5368';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(28.125, -13.275), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ZMB' AND "layerName" = 'glofasStations' AND "referenceId" = 'G1312';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(26.325, -13.725), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ZMB' AND "layerName" = 'glofasStations' AND "referenceId" = 'G1323';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(23.275, -16.125), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ZMB' AND "layerName" = 'glofasStations' AND "referenceId" = 'G1361';
UPDATE "api-service"."geo-feature" SET "geometry" = public.ST_SetSRID(public.ST_MakePoint(23.425, -16.375), 4326), "updated" = CURRENT_TIMESTAMP
WHERE "countryCodeIso3" = 'ZMB' AND "layerName" = 'glofasStations' AND "referenceId" = 'G5696';
