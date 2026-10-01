/* Genererad av tools/gen_contracts.py ur mandatorn_model/constants.py — redigera inte för hand. */
export const PARTIES = ["M", "L", "C", "KD", "S", "V", "MP", "SD"] as const;
export type Party = (typeof PARTIES)[number];
export const PARTY_NAMES: Record<string, string> = {"M": "Moderaterna", "L": "Liberalerna", "C": "Centerpartiet", "KD": "Kristdemokraterna", "S": "Socialdemokraterna", "V": "Vänsterpartiet", "MP": "Miljöpartiet", "SD": "Sverigedemokraterna", "O": "Övriga"};
export const PARTY_COLORS: Record<string, string> = {"M": "#52BDEC", "L": "#006AB3", "C": "#009933", "KD": "#000077", "S": "#E8112D", "V": "#AF0000", "MP": "#83CF39", "SD": "#DDDD00", "O": "#AAAAAA"};
export const BLOC_PARTIES: Record<string, Party[]> = {"Högerblocket": ["M", "L", "KD", "SD"], "Vänsterblocket": ["S", "V", "MP", "C"]};
export const COALITIONS: Record<string, Party[]> = {"Nuv. regering (M + L + KD + SD)": ["M", "L", "KD", "SD"], "Opposition (S + V + MP + C)": ["S", "V", "MP", "C"], "Rödgröna (S + V + MP)": ["S", "V", "MP"], "M + KD + SD (utan L)": ["M", "KD", "SD"], "Mittenblock (S + C + L)": ["S", "C", "L"], "Storkoalition (S + M)": ["S", "M"], "S + MP + C + L": ["S", "MP", "C", "L"]};
export const CONSTITUENCIES: Record<string, { seats: number }> = {"Stockholms stad": {"seats": 29}, "Stockholms län": {"seats": 41}, "Uppsala": {"seats": 12}, "Södermanland": {"seats": 9}, "Östergötland": {"seats": 14}, "Jönköping": {"seats": 11}, "Kronoberg": {"seats": 6}, "Kalmar": {"seats": 7}, "Gotland": {"seats": 2}, "Blekinge": {"seats": 5}, "Malmö": {"seats": 10}, "Skåne V": {"seats": 9}, "Skåne S": {"seats": 12}, "Skåne N/Ö": {"seats": 10}, "Halland": {"seats": 10}, "Göteborg": {"seats": 18}, "VG Västra": {"seats": 11}, "VG Norra": {"seats": 8}, "VG Södra": {"seats": 7}, "VG Östra": {"seats": 8}, "Värmland": {"seats": 9}, "Örebro": {"seats": 9}, "Västmanland": {"seats": 8}, "Dalarna": {"seats": 9}, "Gävleborg": {"seats": 9}, "Västernorrland": {"seats": 7}, "Jämtland": {"seats": 4}, "Västerbotten": {"seats": 8}, "Norrbotten": {"seats": 8}};
export const TOTAL_SEATS = 349;
export const THRESHOLD = 4.0;
export const BASELINE_YEAR = 2026;
export const BASELINE_ELECTION_DATE = "2026-09-13";
export const NEXT_ELECTION_YEAR = 2030;
export const NEXT_ELECTION_DATE = "2030-09-08";
export const VERBAL_SCALE = {"_doc": "Verbal sannolikhetsskala (DECISIONS D3). Enda källan — läses av mandatorn_model/text.py och web/. Gränser: p < below → etikett; sista steget gäller resten. Mittbandet är slutet på båda sidor (0,35 och 0,65 ger 'Jämnt').", "steps": [{"below": 0.1, "label": "Väldigt osannolikt"}, {"below": 0.35, "label": "Osannolikt"}, {"atMost": 0.65, "label": "Jämnt"}, {"atMost": 0.9, "label": "Troligt"}, {"label": "Väldigt troligt"}], "display": {"min": 0.01, "max": 0.99, "belowMin": "<1 %", "aboveMax": ">99 %"}};
