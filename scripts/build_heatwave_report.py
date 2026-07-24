from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
import textwrap

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "pdf"
PDF_PATH = OUT_DIR / "teplovi-khvyli-doslidzhennia.pdf"
TEX_PATH = OUT_DIR / "teplovi-khvyli-doslidzhennia.tex"

TITLE = "Теплові хвилі: моделювання, супутниковий моніторинг і персоналізований ризик для здоров'я"
SUBTITLE = "Науково-технічний документ для MVP сервісу в Україні"
DATE = "23 липня 2026"


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    kind: str
    url: str
    doi: str | None = None


SOURCES = [
    Source("S1", "WHO. Climate change: heat and health", "офіційна медична довідка", "https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health"),
    Source("S2", "WHO. Heatwaves: how to stay cool", "офіційні рекомендації", "https://www.who.int/news-room/questions-and-answers/item/heatwaves-how-to-stay-cool"),
    Source("S3", "WMO. Extreme heat", "офіційна метеорологічна довідка", "https://public.wmo.int/topics/extreme-heat"),
    Source("S4", "WMO. Naming heatwaves and heat-health warnings", "офіційна позиція", "https://wmo.int/media/news/wmo-has-no-immediate-plans-name-heatwaves"),
    Source("S5", "NOAA NESDIS. What is a heat wave?", "офіційна довідка", "https://www.nesdis.noaa.gov/about/k-12-education/understanding-our-planet/what-heat-wave"),
    Source("S6", "Climdex and ETCCDI. Warm Spell Duration Index", "кліматичний індекс", "https://www.rdocumentation.org/packages/climdex.pcic/versions/1.1-11/topics/climdex.wsdi"),
    Source("S7", "Copernicus. Temperature and thermal stress, UTCI", "офіційна кліматична довідка", "https://climate.copernicus.eu/esotc/2023/temperature-and-thermal-stress"),
    Source("S8", "NOAA and NWS. Heat index and heat safety", "офіційні рекомендації", "https://www.weather.gov/btv/heat"),
    Source("S9", "NOAA JetStream. Upper-air charts and wave patterns", "офіційна метеорологічна довідка", "https://www.noaa.gov/jetstream/upper-air-charts/basic-wave-patterns"),
    Source("S10", "AMS Glossary. Heat dome", "метеорологічний словник", "https://glossary.ametsoc.org/wiki/heat-dome/"),
    Source("S11", "Barriopedro et al. Heat Waves: Physical Understanding and Scientific Challenges", "оглядова стаття", "https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2022RG000780", "10.1029/2022RG000780"),
    Source("S12", "Perkins-Kirkpatrick and Gibson. Changes in regional heatwave characteristics as a function of increasing global temperature", "наукова стаття", "https://link.springer.com/article/10.1007/s40641-016-0042-x", "10.1007/s40641-016-0042-x"),
    Source("S13", "WRF Model. NCAR Weather Research and Forecasting Model", "документація моделі", "https://www2.mmm.ucar.edu/wrf/site/index.html"),
    Source("S14", "ECMWF Open Data", "прогнозні дані", "https://www.ecmwf.int/en/forecasts/datasets/open-data"),
    Source("S15", "NOAA NCEI. Global Forecast System", "прогнозні дані", "https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast"),
    Source("S16", "DWD. ICON forecast data", "прогнозні дані", "https://www.dwd.de/EN/ourservices/nwp_forecast_data/nwp_forecast_data.html"),
    Source("S17", "Copernicus CDS. ERA5 hourly data", "реаналіз", "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-timeseries"),
    Source("S18", "Copernicus CDS. ERA5-Land hourly data", "реаналіз", "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries"),
    Source("S19", "Copernicus SentiWiki. Sentinel-3 SLSTR products", "супутниковий продукт", "https://sentiwiki.copernicus.eu/web/slstr-products"),
    Source("S20", "USGS. Landsat Collection 2 Surface Temperature", "супутниковий продукт", "https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature"),
    Source("S21", "NASA LAADS. MODIS MOD11A1 LST", "супутниковий продукт", "https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MOD11A1"),
    Source("S22", "NASA MODAPS. VIIRS VNP21_NRT LST", "супутниковий продукт", "https://modaps.modaps.eosdis.nasa.gov/services/about/products/viirs-land-c2-nrt/VNP21_NRT.html"),
    Source("S23", "EUMETSAT LSA SAF. Land Surface Temperature", "супутниковий продукт", "https://lsa-saf.eumetsat.int/en/data/products/land-surface-temperature-and-emissivity/"),
    Source("S24", "Copernicus Data Space. Sentinel-5P", "супутниковий продукт", "https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-5p"),
    Source("S25", "NASA and USDA SMAP global soil moisture", "супутниковий та асиміляційний продукт", "https://earth.gsfc.nasa.gov/hydro/data/nasa-usda-global-soil-moisture-data"),
    Source("S26", "NASA POWER hourly API", "метеорологічний API", "https://power.larc.nasa.gov/docs/services/api/temporal/hourly/"),
    Source("S27", "Guo et al. Heat Wave and Mortality: A Multicountry, Multicommunity Study", "епідеміологічна стаття", "https://pmc.ncbi.nlm.nih.gov/articles/PMC5783630/", "10.1289/EHP1026"),
    Source("S28", "Ballester et al. Heat-related mortality in Europe during the summer of 2022", "епідеміологічна стаття", "https://www.nature.com/articles/s41591-023-02419-z", "10.1038/s41591-023-02419-z"),
    Source("S29", "Zhao et al. Global, regional, and national burden of mortality associated with non-optimal ambient temperatures", "епідеміологічна стаття", "https://www.thelancet.com/journals/lanplh/article/PIIS2542-5196(21)00081-4/fulltext", "10.1016/S2542-5196(21)00081-4"),
    Source("S30", "Alahmad et al. Associations Between Extreme Temperatures and Cardiovascular Cause-Specific Mortality", "епідеміологічна стаття", "https://pmc.ncbi.nlm.nih.gov/articles/PMC9794133/", "10.1161/CIRCULATIONAHA.122.061832"),
    Source("S31", "Chen et al. Impact of Heat Wave Definitions on Cardiovascular Mortality in Beijing", "епідеміологічна стаття", "https://pmc.ncbi.nlm.nih.gov/articles/PMC5036765/", "10.3390/ijerph13090933"),
    Source("S32", "Silveira et al. Heat wave and mortality in Rio de Janeiro", "епідеміологічна стаття", "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0283899", "10.1371/journal.pone.0283899"),
    Source("S33", "Lee et al. The Effects of Temperature on Kidney Morbidity", "систематичний огляд", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6378387/", "10.3961/jpmph.18.149"),
    Source("S34", "Remigio et al. Extreme heat and outcomes among patients with end-stage renal disease", "епідеміологічна стаття", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6692691/", "10.1001/jamanetworkopen.2019.8904"),
    Source("S35", "Chapman et al. Hyperthermia, dehydration and acute kidney injury biomarkers", "експериментальна стаття", "https://journals.physiology.org/doi/abs/10.1152/japplphysiol.00787.2019", "10.1152/japplphysiol.00787.2019"),
    Source("S36", "Cedeño Laurent et al. Reduced cognitive function during a heat wave", "когортне спостереження", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6039003/", "10.1371/journal.pmed.1002605"),
    Source("S37", "Obradovich et al. Nighttime temperature and human sleep loss", "епідеміологічна стаття", "https://pmc.ncbi.nlm.nih.gov/articles/PMC5446217/", "10.1126/sciadv.1601555"),
    Source("S38", "Shibasaki et al. Suppression of cognitive function in hyperthermia", "експериментальна стаття", "https://pubmed.ncbi.nlm.nih.gov/28497797/", "10.1038/srep43528"),
    Source("S39", "Chersich et al. High temperature in pregnancy and adverse birth outcomes", "систематичний огляд", "https://pmc.ncbi.nlm.nih.gov/articles/PMC7610201/", "10.1136/bmj.m3811"),
    Source("S40", "Cho et al. A deep learning-based land-atmosphere coupled model for heatwave prediction", "модельна стаття", "https://doaj.org/article/9d72fc5172f54470829624f474c76fce", "10.1038/s41612-025-01311-6"),
    Source("S41", "Weirich-Benet et al. Subseasonal prediction of Central European summer heatwaves", "модельна стаття", "https://journals.ametsoc.org/view/journals/aies/2/2/AIES-D-22-0038.1.xml", "10.1175/AIES-D-22-0038.1"),
    Source("S42", "Hou et al. Spatial characterization of global heat waves using satellite-based LST", "дистанційне зондування", "https://doaj.org/article/1e54a15d126944b48726e0a5395f34b4", "10.1016/j.jag.2023.103604"),
    Source("S43", "Ghatak et al. The role of local heating in the 2015 Indian Heat Wave", "дистанційне зондування та реаналіз", "https://www.nature.com/articles/s41598-017-07956-5", "10.1038/s41598-017-07956-5"),
    Source("S44", "Hidalgo Garcia et al. Spatiotemporal analysis of urban thermal effects caused by heatwaves", "дистанційне зондування", "https://digibug.ugr.es/handle/10481/77763", "10.3390/su141912262"),
    Source("S45", "Rees et al. Kharkiv urbanization and urban heat island from remote sensing", "Україна, дистанційне зондування", "https://www.mdpi.com/2072-4292/16/9/1637", "10.3390/rs16091637"),
    Source("S46", "Ukrainian Hydrometeorological Center", "національний метеорологічний орган", "https://www.meteo.gov.ua/en/"),
    Source("S47", "CDC. Heat and medications: guidance for clinicians", "медичні рекомендації", "https://www.cdc.gov/heat-health/hcp/clinical-guidance/heat-and-medications-guidance-for-clinicians.html"),
    Source("S48", "CDC. Heat-related illness prevention", "медичні рекомендації", "https://www.cdc.gov/extreme-heat/prevention/index.html"),
    Source("S49", "NHS. Heatwave: how to cope in hot weather", "медичні рекомендації", "https://www.nhs.uk/live-well/seasonal-health/heatwave-how-to-cope-in-hot-weather/"),
    Source("S50", "NHS. Heat exhaustion and heatstroke", "медичні рекомендації", "https://www.nhs.uk/conditions/heat-exhaustion-heatstroke/"),
    Source("S51", "Shevchenko. Human Thermal Comfort Conditions during Heat Wave Events in Kyiv, Ukraine", "Україна, біоклімат і тепловий стрес", "https://erem.ktu.lt/index.php/erem/article/view/23142", "10.5755/j01.erem.77.2.23142"),
    Source("S52", "Heaviside, Vardoulakis and Cai. Attribution of mortality to the urban heat island during heatwaves in the West Midlands, UK", "просторова оцінка смертності та UHI", "https://link.springer.com/article/10.1186/s12940-016-0100-9", "10.1186/s12940-016-0100-9"),
    Source("S53", "Hondula et al. Geographic dimensions of heat-related mortality in seven U.S. cities", "просторова оцінка смертності", "https://pubmed.ncbi.nlm.nih.gov/25791867/", "10.1016/j.envres.2015.02.033"),
    Source("S54", "Ma et al. Investigating urban heat-related health risks based on local climate zones", "LCZ risk zoning", "https://www.iges.or.jp/en/pub/lcz-healthrisks/en"),
    Source("S55", "WHO Europe. Ukraine: 2026 Summer risk assessment", "Україна, оцінка літніх ризиків", "https://www.who.int/europe/publications/i/item/WHO-EURO-2026-12414-52188-83065"),
    Source("S56", "ECMWF. AIFS Machine Learning data", "операційні AI-прогнози", "https://www.ecmwf.int/en/forecasts/datasets/aifs-machine-learning-data"),
    Source("S57", "Lam et al. GraphCast: Learned Global Weather Forecasting", "graph neural network для прогнозу погоди", "https://deepmind.google/research/publications/22598/", "10.1126/science.adi2336"),
    Source("S58", "Bi et al. Accurate medium-range global weather forecasting with 3D neural networks", "Pangu-Weather, 3D deep networks", "https://www.nature.com/articles/s41586-023-06185-3", "10.1038/s41586-023-06185-3"),
    Source("S59", "Kurth et al. FourCastNet: Accelerating Global High-Resolution Weather Forecasting Using Adaptive Fourier Neural Operators", "Fourier neural operator", "https://dl.acm.org/doi/10.1145/3592979.3593412", "10.1145/3592979.3593412"),
    Source("S60", "Price et al. Probabilistic weather forecasting with machine learning", "GenCast, diffusion ensemble forecast", "https://www.nature.com/articles/s41586-024-08252-9", "10.1038/s41586-024-08252-9"),
    Source("S61", "Kochkov et al. Neural general circulation models for weather and climate", "NeuralGCM, hybrid differentiable model", "https://www.nature.com/articles/s41586-024-07744-y", "10.1038/s41586-024-07744-y"),
    Source("S62", "Moldovan et al. AIFS Single 1.1.0: an update to ECMWF's machine-learned weather forecast model AIFS", "операційна ML weather model", "https://gmd.copernicus.org/articles/19/4703/2026/", "10.5194/gmd-19-4703-2026"),
    Source("S63", "Zhu et al. Integrating geographic knowledge into deep learning for spatiotemporal local climate zone mapping", "LCZ mapping і міське тепло", "https://www.sciencedirect.com/science/article/pii/S0924271624003162", "10.1016/j.isprsjprs.2024.08.004"),
    Source("S64", "Kuo et al. Utilizing machine learning for predicting mortality in patients with heat-related illness who visited the emergency department", "heat-related illness prediction", "https://pubmed.ncbi.nlm.nih.gov/40319661/", "10.1016/j.ijmedinf.2025.105951"),
    Source("S65", "Toure et al. Machine Learning-Based Prediction of Heatwave-Related Hospitalizations: A Case Study in Matam, Senegal", "heatwave-related hospitalization prediction", "https://pubmed.ncbi.nlm.nih.gov/41007493/", "10.3390/ijerph22091349"),
    Source("S66", "Rojas-Valverde et al. Wearable Sensor Technology to Predict Core Body Temperature: A Systematic Review", "wearables і heat strain", "https://pubmed.ncbi.nlm.nih.gov/36236737/"),
]

VARIABLE_MARKUP = [
    ("T_max", "T<sub>max</sub>", r"$T_{\max}$"),
    ("T_min", "T<sub>min</sub>", r"$T_{\min}$"),
    ("TX_90", "TX<sub>90</sub>", r"$TX_{90}$"),
    ("TX_95", "TX<sub>95</sub>", r"$TX_{95}$"),
    ("TX_99", "TX<sub>99</sub>", r"$TX_{99}$"),
    ("TN_90", "TN<sub>90</sub>", r"$TN_{90}$"),
    ("T2m", "T<sub>2m</sub>", r"$T_{2m}$"),
    ("Z500", "Z<sub>500</sub>", r"$Z_{500}$"),
    ("PM2.5", "PM<sub>2.5</sub>", r"$PM_{2.5}$"),
]


BLOCKS: list[dict] = [
    {"type": "toc", "items": [
        "Executive summary",
        "Позначення змінних",
        "Що таке теплова хвиля",
        "Фізика формування",
        "Роль антициклонів",
        "Чи підходить модель Гауса",
        "Найкращі моделі для різних завдань",
        "Глибоке навчання у сервісі",
        "Супутники та джерела даних",
        "Зонування теплової хвилі та зони ризику для здоров'я",
        "Таблиця змінних та індексів",
        "Вплив на здоров'я",
        "Аналіз наукових статей",
        "Архітектура застосунку",
        "Персональна модель ризику",
        "Рекомендації користувачам",
        "Український контекст",
        "Обмеження та етичні ризики",
        "План реалізації MVP",
        "Список джерел",
    ]},
    {"type": "section", "title": "Executive summary"},
    {"type": "p", "text": "Теплова хвиля - це не просто висока абсолютна температура. Науково коректне визначення повинно бути локальним: поріг має залежати від кліматології регіону, сезону, тривалості, нічного охолодження, вологості та вразливості населення. Для України доцільно стартувати з комбінованої дефініції: щонайменше 3 послідовні дні у теплий сезон, коли добова максимальна температура перевищує локальний 90-й або 95-й перцентиль базового періоду 1991-2020, з окремими тригерами для тропічних ночей, T_min >= 20 °C, високого UTCI або Heat Index, та накопичення тепла за Excess Heat Factor [S1-S8]."},
    {"type": "p", "text": "Фізично теплові хвилі підтримуються взаємодією циркуляції атмосфери, радіаційного балансу і стану поверхні. Антициклон і атмосферне блокування часто створюють умови для ясного неба, низхідних рухів, малої хмарності, слабкого перемішування та тривалої адвекції теплого повітря. Але антициклон не є просто 'масою повітря, притиснутою до поверхні': це тривимірна циркуляційна структура, пов'язана з полями тиску, геопотенціальної висоти, вітру, вертикальної швидкості та хвиль Россбі [S9-S12]."},
    {"type": "p", "text": "Для MVP не потрібно розв'язувати повну атмосферну задачу самостійно. Практичний стек: ERA5-Land для кліматології та порогів, ECMWF Open Data, GFS та ICON для прогнозу, Sentinel-3, MODIS, VIIRS та Landsat для LST, NDVI і міського острова тепла, PostGIS та TimescaleDB для просторово-часових даних, Python, xarray, rasterio та Dask для обробки, FastAPI, React та MapLibre для сервісу [S13-S26]."},
    {"type": "p", "text": "Медичний ризик треба подавати як evidence-informed decision support, а не як діагноз. Сильні докази є для зростання смертності, серцево-судинних подій, ниркових ускладнень, теплового виснаження та теплового удару, порушення сну і когнітивного погіршення під час спеки. Помірні докази - для тромбозу, інсульту, метаболічних загострень та психічних наслідків. Для індивідуальних медичних прогнозів потрібна клінічна валідація [S27-S39, S47-S50]."},

    {"type": "section", "title": "Позначення змінних"},
    {"type": "p", "text": "Щоб документ не виглядав як набір уривчастих кодів, нижче введено єдині позначення. У формулах і правилах MVP використовуються саме ці змінні."},
    {"type": "table", "title": "Основні позначення", "headers": ["Змінна", "Значення", "Практичне використання"], "rows": [
        ["T_max", "добова максимальна температура повітря на висоті 2 м", "виявлення денного екстремуму та прогноз небезпеки"],
        ["T_min", "добова мінімальна нічна температура повітря на висоті 2 м", "оцінка нічного охолодження та ризику сну"],
        ["TX_90", "90-й перцентиль добової максимальної температури для місцевої кліматології", "ранній сигнал теплової хвилі"],
        ["TX_95", "95-й перцентиль добової максимальної температури для місцевої кліматології", "основний поріг небезпечної теплової хвилі"],
        ["TX_99", "99-й перцентиль добової максимальної температури для місцевої кліматології", "екстремальний рівень спеки"],
        ["TN_90", "90-й перцентиль добової мінімальної температури", "нічний тригер ризику"],
        ["EHF", "Excess Heat Factor", "накопичення тепла та короткочасна акліматизація"],
        ["UTCI", "Universal Thermal Climate Index", "основний індекс теплового стресу надворі"],
        ["WBGT", "Wet-Bulb Globe Temperature", "оцінка ризику для роботи, спорту та сонячного навантаження"],
        ["LST", "температура земної поверхні з супутникових продуктів", "карта міського перегріву та поверхневого острова тепла"],
        ["MSLP", "тиск на рівні моря", "діагностика антициклонів і баричних полів"],
        ["Z500", "геопотенціальна висота на рівні 500 гПа", "діагностика ridge, blocking та heat dome"],
        ["SM", "вологість ґрунту", "передумова drought-heat feedback"],
        ["NDVI", "індекс рослинності", "зелена інфраструктура та локальне охолодження"],
        ["UHI", "міський острів тепла", "міська поправка до персонального ризику"],
    ]},

    {"type": "section", "title": "Що таке теплова хвиля"},
    {"type": "p", "text": "Універсального визначення теплової хвилі немає. NOAA описує її як період незвично спекотної погоди щонайменше 2 дні для конкретної місцевості. WMO та WHO роблять наголос на кількох послідовних днях і ночах аномальної спеки, що перевищує місцеву кліматичну норму та створює ризик для здоров'я. ETCCDI використовує Warm Spell Duration Index: щонайменше 6 послідовних днів, коли денна максимальна температура перевищує 90-й перцентиль календарно-залежної кліматології [S3-S6]."},
    {"type": "p", "text": "Абсолютні пороги на кшталт T_max >= 30 °C або T_max >= 35 °C прості для попереджень, але погано переносяться між регіонами. День з T_max 31 °C може бути звичним для півдня України і екстремальним для високогір'я Карпат. Тому для виявлення подій краще використовувати відносні пороги: 90-й перцентиль для раннього сигналу, 95-й для небезпечної хвилі, 99-й для екстремальної події. Абсолютні пороги варто залишити як додаткові публічні тригери."},
    {"type": "p", "text": "Вологість, точка роси, apparent temperature, wet-bulb temperature, wet-bulb globe temperature та heat index не замінюють температуру повітря, але краще відображають теплове навантаження на людину. Висока вологість зменшує ефективність випаровування поту; слабкий вітер і сонячна радіація підвищують ризик на відкритому повітрі; висока нічна температура перешкоджає відновленню організму і охолодженню будівель [S7, S8]."},
    {"type": "callout", "title": "Рекомендована дефініція для України", "text": "Базова подія: щонайменше 3 послідовні дні з T_max > TX_95 для конкретної комірки або району за кліматологією 1991-2020. Рівень 'ранній сигнал': щонайменше 3 дні з T_max > TX_90. Рівень 'екстремально': T_max > TX_99 або UTCI у категорії very strong heat stress чи extreme heat stress. Додатковий нічний тригер: T_min >= 20 °C або T_min > TN_90. Для міст додати поправку на UHI, LST і поверх будівлі."},
    {"type": "table", "title": "Підходи до визначення теплової хвилі", "headers": ["Підхід", "Що вимірює", "Переваги", "Недоліки"], "rows": [
        ["Абсолютний поріг", "T_max або T_min вище фіксованого значення", "Простий для попереджень і медіа", "Не враховує локальну акліматизацію"],
        ["Перцентильний поріг", "Перевищення 90-го, 95-го або 99-го перцентиля локальної кліматології", "Порівнюваний між регіонами, добрий для науки", "Потребує якісної історії даних"],
        ["Тривалість", "2, 3, 4, 5 або 6 днів поспіль", "Враховує накопичення тепла", "Результати залежать від вибору тривалості"],
        ["Нічний компонент", "T_min, tropical nights, TN_90", "Відображає відсутність відновлення", "Потрібна локальна інтерпретація"],
        ["Фізіологічний індекс", "HI, Humidex, WBGT, UTCI, EHF", "Ближче до ризику для людини", "Потребує більше змінних і припущень"],
    ]},

    {"type": "section", "title": "Фізика формування"},
    {"type": "p", "text": "Теплова хвиля зазвичай не має одного механізму. Вона виникає, коли циркуляційна аномалія, радіаційний режим і поверхневі умови працюють в одному напрямку. Атмосферне блокування може утримувати ridge високого тиску кілька днів або тижнів. Хвилі Россбі та струменева течія визначають форму і швидкість переміщення таких аномалій. Коли струменева течія сильно меандрує або стає квазистаціонарною, тепла повітряна маса може залишатися над одним регіоном довше [S9-S12]."},
    {"type": "p", "text": "У середніх широтах вітер вище приземного шару часто близький до геострофічного балансу: сила градієнта тиску врівноважується силою Коріоліса. Через обертання Землі повітря не просто рухається від високого тиску до низького; воно огинає області тиску. Тому антициклональна циркуляція - це не статична 'кришка', а динамічна структура, яку треба бачити у полях MSLP, Z500, вітру та вертикальної швидкості."},
    {"type": "p", "text": "Низхідні рухи у ridge та антициклоні адіабатично нагрівають повітря і знижують відносну вологість. Менша хмарність збільшує короткохвильову сонячну радіацію біля поверхні. Сухий ґрунт зменшує евапотранспірацію, тому частка енергії йде у sensible heat flux замість latent heat flux. Це створює позитивний зворотний зв'язок: сухіший ґрунт - вища температура - більша потреба у випаровуванні - ще сухіший ґрунт [S11, S12, S40]."},
    {"type": "p", "text": "Міський острів тепла посилює нічне навантаження: щільна забудова, темні поверхні, мала рослинність, антропогенне тепло і слабке провітрювання збільшують накопичення тепла. У період теплової хвилі поверхнева UHI може посилюватися, але величина залежить від типу міста, зелених зон, вологості ґрунту навколо міста і часу доби [S42-S45]."},
    {"type": "table", "title": "Механізми та рівень доказів", "headers": ["Механізм", "Роль", "Оцінка доказів"], "rows": [
        ["Блокування атмосфери", "Утримує циркуляційний патерн і затримує фронти", "докази сильні"],
        ["Хвилі Россбі і jet stream", "Формують ridge та trough структуру і стаціонарність", "докази сильні"],
        ["Адіабатичне нагрівання", "Повітря теплішає при низхідному стисканні", "докази сильні як фізичний механізм"],
        ["Суха поверхня", "Зменшує evapotranspiration і збільшує sensible heat", "докази сильні"],
        ["Адвекція гарячого повітря", "Переносить теплу та суху повітряну масу", "докази сильні"],
        ["SST і телеконекції", "Можуть змінювати імовірність циркуляційних режимів", "докази помірні, регіонально залежні"],
        ["Пожежі й аерозолі", "Змінюють радіацію та якість повітря; вплив на T неоднозначний", "докази помірні"],
        ["Кліматична зміна", "Зсуває розподіл температур і збільшує інтенсивність екстремумів", "докази сильні"],
    ]},

    {"type": "section", "title": "Роль антициклонів"},
    {"type": "quote", "text": "Початкове припущення: антициклон - це велика маса повітря з високим тиском, яка опускається, притискається до поверхні та нагрівається, не маючи змоги піднятися наверх."},
    {"type": "p", "text": "Що правильно: в антициклональних ситуаціях часто є низхідні рухи; повітря при опусканні стискається і нагрівається сухоадіабатично; це пригнічує конвекцію, хмарність і опади. За ясного неба денна інсоляція збільшується, а сухий ґрунт швидко перетворює енергію на нагрів повітря."},
    {"type": "p", "text": "Що спрощено: антициклон не є однорідною масою, яка механічно 'притискається'. У приземному шарі тертя дозволяє слабкий рух повітря назовні від центру високого тиску; вище вітер переважно обертається навколо ізобар. Для теплової хвилі часто важливий не сам приземний максимум тиску, а глибокий ridge у середній тропосфері, омега-блокування або heat dome [S9, S10]."},
    {"type": "p", "text": "Що треба виправити у формулюванні: повітря не 'не має змоги піднятися' абсолютно. Конвекція пригнічується через стабільну стратифікацію та subsidence inversion, але локальні грози, бризи, гірсько-долинні циркуляції або фронтальні збурення можуть її порушити. Для сервісу антициклон треба діагностувати через поля MSLP, Z500, vorticity, omega, wind і persistence, а не через супутникову картинку."},

    {"type": "section", "title": "Чи підходить модель Гауса"},
    {"type": "table", "title": "Варіанти 'моделі Гауса' і придатність", "headers": ["Варіант", "Що описує", "Чи корисно для теплових хвиль", "Обмеження"], "rows": [
        ["Гаусівський шлейф", "Розсіювання домішки від точкового джерела у стаціонарному вітрі", "Може оцінювати дим та забруднення під час спеки", "Не моделює антициклон, тиск, обертання Землі, радіацію, вологу"],
        ["Гаусівська модель розсіювання", "Поширення концентрацій у приземному шарі", "Корисна для пожежного диму або промислових викидів", "Не описує heatwave dynamics"],
        ["Гаусівський просторовий розподіл", "Ідеалізовану 'пляму' аномалії", "Може бути простим synthetic test", "Реальні хвилі асиметричні та залежать від циркуляції"],
        ["Нормальний розподіл аномалій", "Статистику температурних відхилень", "Корисний для базових z-score", "Погано описує хвости; потрібні перцентилі або EVT"],
        ["Gaussian Process", "Непараметричну регресію з невизначеністю", "Добре для інтерполяції, bias correction та probabilistic maps", "Дорогий на великих сітках; потребує sparse або approximate GP"],
    ]},
    {"type": "p", "text": "Висновок: гаусівський шлейф не підходить для повноцінного моделювання антициклону. Gaussian Processes можуть бути цінним компонентом сервісу, але як статистичний шар для корекції прогнозу, spatial interpolation або оцінки невизначеності, а не як фізична модель атмосфери."},

    {"type": "section", "title": "Найкращі моделі для різних завдань"},
    {"type": "table", "title": "Модельний стек за складністю", "headers": ["Завдання", "Достатній MVP-рівень", "Коли потрібен складніший рівень"], "rows": [
        ["Виявлення поточної хвилі", "ERA5-Land та станції, TX_90, TX_95, T_min і EHF", "Якщо потрібна квартальна міська деталізація"],
        ["Прогноз на 1-3 дні", "ECMWF IFS, ECMWF AIFS, GFS та ICON з локальною нейронною корекцією bias", "Для nowcasting у містах потрібні станції, LST і UHI downscaling"],
        ["Прогноз на 7-14 днів", "ECMWF AIFS ENS, ECMWF ENS, GenCast-подібні ensemble maps та ймовірність перевищення порогів", "Subseasonal transformer або circulation-pattern model"],
        ["Моделювання антициклону", "Аналіз MSLP, Z500, wind та omega з NWP і reanalysis", "Повне NWP або WRF для сценаріїв"],
        ["Міський тепловий ризик", "U-Net або Swin Transformer для downscaling LST, LCZ, NDVI і building density", "WRF urban canopy або CFD тільки для мікрорайонів"],
        ["Персональний медичний ризик", "Мультимодальна neural risk model з rule-based safety guardrails", "Клінічно валідована модель після локальних медичних даних"],
    ]},
    {"type": "p", "text": "Primitive equations і чисельні моделі погоди вже реалізовані в ECMWF IFS, GFS, ICON і WRF. Вони розв'язують рівняння руху, термодинаміки, маси й вологи у наближеннях, придатних для атмосфери. Станом на 23 липня 2026 року deep learning вже не є лише експериментом: ECMWF AIFS працює операційно, а GraphCast, Pangu-Weather, GenCast, FourCastNet і NeuralGCM показали, що neural weather models можуть бути швидкими та сильними для середньострокового прогнозу [S56-S62]."},
    {"type": "equation", "text": "P(heatwave at location x, lead t) = P(T_max_forecast(x,t) > TX_95(x) for at least 3 days)"},

    {"type": "section", "title": "Глибоке навчання у сервісі"},
    {"type": "p", "text": "Deep learning треба використовувати не як декоративну заміну простій формулі, а як окремий шар системи. Найкраща MVP-логіка: брати глобальні AI-прогнози AIFS як operational input; поверх них навчити український постпроцесинг для T_max, T_min, UTCI і ймовірності теплової хвилі; окремо навчити міський downscaling для Києва та інших міст; після появи медичних даних навчити нейронну модель впливу на здоров'я. Це дає складну модель там, де вона корисна, і не створює фальшивої медичної точності."},
    {"type": "p", "text": "GraphCast використовує graph neural network і багатомасштабну сітку, прогнозує 227 атмосферних змінних на 10 днів з кроком 6 год на 0.25° та у публічній оцінці перевищував ECMWF HRES на більшості цілей і часових горизонтів [S57]. Pangu-Weather використовує 3D Earth-specific Transformer, навчений на 39 роках ERA5; автори показали сильну детерміновану якість прогнозу і корисність для екстремальної погоди [S58]. GenCast додає головне для ризикового сервісу: ймовірнісний diffusion ensemble на 15 днів, тобто можна рахувати не одну лінію температури, а розподіл сценаріїв [S60]."},
    {"type": "p", "text": "Для теплових хвиль важливо, що не всі neural weather models однаково бачать land feedback. Cho et al. показали, що модель із soil moisture і soil temperature та multi-step loss покращувала heatwave forecast accuracy на 5.9-11.2% порівняно з atmosphere-only моделлю [S40]. Це прямо підтримує рішення включити ERA5-Land, SMAP, LST і вологість ґрунту в neural pipeline."},
    {"type": "table", "title": "Де deep learning реально потрібен", "headers": ["Підзадача", "Архітектура", "Вхідні дані", "Вихід", "Ризик"], "rows": [
        ["Завантаження AI-прогнозу", "ECMWF AIFS ENS як готова операційна модель", "AIFS, IFS, GFS, ICON, ERA5-Land", "ensemble T_max, T_min, wind, humidity, Z500", "Низький ризик для MVP, бо модель уже працює операційно [S56, S62]"],
        ["Сегментація теплової хвилі", "U-Net, ConvLSTM або Earthformer", "поля T_max, T_min, Z500, MSLP, soil moisture, radiation", "маска теплової хвилі на 1-7 днів", "Потрібна перевірка на hindcast України"],
        ["Ймовірнісний прогноз", "diffusion ensemble або deep ensemble", "останній стан атмосфери і прогнозні ознаки", "ймовірність TX_95, TX_99, EHF і tropical nights", "Детерміновані моделі можуть згладжувати екстремуми"],
        ["Міський downscaling", "U-Net, ResNet або Swin Transformer", "Sentinel-3, MODIS, VIIRS, Landsat, NDVI, LCZ, забудова, elevation", "30-100 м карта LST і корекція температури повітря", "Потрібні станції для перевірки температури повітря"],
        ["Картування LCZ", "ResNet50, multi-source fusion або transformer", "Sentinel-1, Sentinel-2, Landsat, контури будівель, OSM", "локальні кліматичні зони міста", "Transfer learning потрібен для України [S63]"],
        ["Персональна модель ризику", "tabular transformer і fusion network", "профіль, ліки, активність, житло, weather embeddings", "категорія ризику та пояснення", "Потрібна клінічна валідація перед user-facing claims"],
        ["Heat strain з wearable", "temporal neural model або hybrid physiological model", "heart rate, skin temperature, activity, ambient T, RH", "ранній сигнал перегріву для спортсменів і працівників", "Потрібна згода користувача і якісна валідація сенсорів [S66]"],
    ]},
    {"type": "equation", "text": "HeatWaveNet:\n  H_t = encoder(weather_fields[t-48h:t], land_state, urban_layers)\n  Y = decoder(H_t)\n  Y = {heatwave_mask, T_max_quantiles, T_min_quantiles, UTCI_quantiles, uncertainty}"},
    {"type": "equation", "text": "DeepRisk:\n  R = fusion(weather_embedding, urban_embedding, user_profile, exposure_context)\n  outputs = {risk_category, risk_interval, top_explanations, safety_guardrails}"},
    {"type": "p", "text": "Ключова архітектура для України: AIFS ENS або IFS ENS дає ймовірнісний прогноз на 15 днів; локальна HeatWaveNet виправляє bias і рахує перевищення локальних порогів TX_90, TX_95, TX_99 та TN_90; UrbanNet уточнює місто за LST, LCZ, NDVI, щільністю забудови і висотою будинків; DeepRisk поєднує це з профілем користувача. Рекомендації все одно має видавати окремий rule engine, бо медичні дії повинні бути контрольовані джерелами WHO, CDC, NHS і локальними лікарями."},
    {"type": "p", "text": "Навчання: ERA5-Land 1991-2020 для кліматології; 2021-2024 validation; 2025-2026 test або rolling hindcast. Loss для forecast layer: quantile loss для T_max і T_min, focal loss для рідкісних extreme events, Dice loss для просторової маски хвилі, CRPS для ймовірнісного прогнозу. Для персонального risk layer: ordinal classification loss, class-balanced sampling, missingness embeddings, monotonic constraints для віку та важких хвороб, uncertainty через deep ensembles і conformal prediction."},
    {"type": "p", "text": "Докази для deep learning сильні для швидкого weather forecasting і помірні для heatwave-specific prediction. Докази помірні для LCZ mapping і LST downscaling. Докази обмежені для персонального health-risk prediction у споживчому застосунку, бо доступні дослідження теплової хвороби частіше працюють з hospital або emergency department data, а не з домашніми користувачами до появи симптомів [S64-S66]. Отже neural risk model можна будувати, але треба прямо позначити: потрібна додаткова клінічна валідація."},

    {"type": "section", "title": "Супутники та джерела даних"},
    {"type": "p", "text": "Дані треба розділяти на чотири класи: прямі супутникові спостереження, реаналізи, прогнозні продукти та похідні індекси. Супутник напряму бачить радіацію, хмарність, LST, NDVI, дим, аерозолі або вологість ґрунту через retrieval та assimilation. Він не бачить антициклон як об'єкт; антициклон визначають за полями атмосферного тиску, геопотенціальної висоти, вітру, вертикального руху і циркуляції з моделей та реаналізів [S17-S26]."},
    {"type": "table", "title": "Основні джерела для України", "headers": ["Джерело", "Тип", "Змінні", "Роздільність та частота", "Затримка та API", "Придатність"], "rows": [
        ["Sentinel-3 SLSTR", "супутник", "LST, brightness temperature, FRP, AOD", "thermal 1 км; solar 500 м; кілька проходів на добу для S3A та S3B", "NRT <3 год, NTC <1 міс; Copernicus Data Space", "Добре для LST, clear-sky, Україна покрита"],
        ["Landsat 8 та Landsat 9 TIRS", "супутник", "Surface temperature, SR, NDVI", "30 м ST product, thermal resampled; разом 8 днів", "USGS API, COG і GeoTIFF; затримка дні", "Найкраще для UHI і квартальної деталізації"],
        ["MODIS Terra та Aqua", "супутник", "денна та нічна LST, emissivity", "1 км daily", "NASA LAADS, Earthdata і HDF", "Стабільний історичний ряд з 2000"],
        ["VIIRS Suomi NPP та JPSS", "супутник", "LST, fires, night lights", "750 м NASA або 375 м NOAA LST; daily та NRT", "Earthdata, MODAPS і NOAA", "Корисно для оперативності і пожеж"],
        ["Meteosat SEVIRI LSA SAF", "геостаціонарний супутник", "LST, emissivity, radiation products", "~3 км, 15 хв інструментальний цикл", "EUMETSAT, LSA SAF і NRT", "Дуже корисно для добового циклу над Україною"],
        ["Sentinel-5P TROPOMI", "супутник", "NO2, CO, O3, aerosol index, clouds", "км-клас, daily", "Copernicus Data Space, NetCDF", "Якість повітря і дим, не температура"],
        ["SMAP", "супутник та assimilation", "soil moisture", "36 км або 9 км, 2-3 дні", "NASA Earthdata, HDF і GeoTIFF", "Передумова drought-heatwave"],
        ["ERA5", "реаналіз", "T2m, Td, RH, wind, radiation, MSLP, Z500, soil", "~31 км hourly", "CDS API; затримка кілька днів; 1940+", "База для циркуляції і кліматології"],
        ["ERA5-Land", "реаналіз", "T2m, soil moisture, radiation, runoff, snow", "~9 км hourly", "CDS API; 1950+", "База для локальних порогів в Україні"],
        ["ECMWF, GFS та ICON", "прогноз", "T2m, T_max, T_min, wind, humidity, pressure, Z500, precipitation", "0.25° або ~13 км; 4 цикли на добу", "GRIB2 і Open Data", "Основа 1-14 денного прогнозу"],
        ["NASA POWER", "похідний API", "T2M, RH, dew point, wind, radiation", "точкові та сіткові дані; hourly", "JSON, CSV і NetCDF", "Швидкий fallback для прототипу"],
    ]},

    {"type": "section", "title": "Зонування теплової хвилі та зони ризику для здоров'я"},
    {"type": "p", "text": "Для сервісу критично розділяти дві різні карти: карту самої теплової хвилі та карту ризику для здоров'я. Перша карта показує метеорологічний контур хвилі: де T_max, T_min, UTCI або EHF перевищують локальні пороги протягом потрібної кількості днів. Друга карта показує зони ризику для здоров'я: де теплова небезпека накладається на населення, забудову, вік, хвороби, доступ до охолодження, нічну температуру та міський острів тепла. Тому теплова хвиля може охопити Київ і частину області, але медичний ризик буде різним у центрі міста, в зелених районах, на промислових територіях, у висотних будинках і в передмістях."},
    {"type": "p", "text": "Дослідження для Києва вже показує, що теплові хвилі можна класифікувати за інтенсивністю теплового стресу, а не лише за температурою. Shevchenko аналізувала Kyiv heat waves за 1961-2020 роки через PET і RayMan: було виявлено 24 події тривалістю 6-18 днів; heat stress варіював від slight до extreme; найсильніша подія припала на кінець липня та першу половину серпня 2010 року [S51]. Це означає, що для Києва потрібен не тільки поріг T_max, а й індекс теплового комфорту та тривалість."},
    {"type": "p", "text": "Міжнародні health-zonation дослідження підтверджують, що просторовий ризик всередині міста не є рівномірним. У West Midlands моделювання показало, що UHI міг дати близько половини heat-related mortality під час хвилі 2003 року; якщо брати просту географічну середню температуру, exposure недооцінюється приблизно на 1 °C, що приблизно відповідає 20% недооцінки mortality [S52]. У семи містах США statistically significant mortality increases були обмежені лише 12-44% postal codes кожного міста, а відомі risk factors пояснювали тільки 14-34% просторової мінливості [S53]."},
    {"type": "p", "text": "Локальні кліматичні зони дають практичний спосіб зонування. LCZ розділяє місто на типи міського середовища: компактна висотна забудова, компактна середньоповерхова забудова, відкрита малоповерхова забудова, промислові території, щільні дерева, вода та інші. У Changzhou оцінювання ризику на основі LCZ показало, що щонайменше 60% зон LCZ1-LCZ5 були зонами високого ризику [S54]. Для Києва аналогічна логіка дозволяє не малювати одне попередження на всю адміністративну територію, а виділяти райони з високою тепловою небезпекою, високою експозицією і високою вразливістю."},
    {"type": "table", "title": "Як будувати зонування для Києва", "headers": ["Шар", "Що показує", "Дані", "Результат"], "rows": [
        ["Контур теплової хвилі", "де є сама метеорологічна подія", "ERA5-Land, ECMWF, GFS, ICON, T_max, T_min, TX_95, TN_90", "полігон або растрова маска теплової хвилі"],
        ["Зона теплового стресу", "де людині фізіологічно важко перебувати надворі", "UTCI, PET, WBGT, відносна вологість, вітер, сонячна радіація", "зони теплового стресу надворі"],
        ["Міська зона перегріву поверхні", "де поверхня та забудова підсилюють перегрів", "Landsat, Sentinel-3, MODIS, VIIRS, LST, NDVI, частка непроникної поверхні", "карта міського острова тепла і перегрітих районів"],
        ["Зона експозиції населення", "де реально перебуває багато людей", "сітка населення, мобільна активність якщо доступно, житлова забудова, робочі зони", "карта кількості людей під впливом"],
        ["Зона вразливості", "де люди більш чутливі до спеки", "вік, хронічні хвороби, соціальна ізоляція, доступ до води та охолодження", "карта вразливості здоров'я"],
        ["Персональна зона ризику", "як зона впливає на конкретну людину", "профіль користувача, локація, поверх, кондиціонер, ліки, активність", "персональний бал ризику і рекомендації"],
    ]},
    {"type": "callout", "title": "Висновок для Києва", "text": "Якщо теплова хвиля знаходиться над Києвом, вона не впливає однаково на всіх мешканців і не зупиняється на адміністративному кордоні. Для застосунку треба моделювати контур хвилі для Києва та області, а всередині цього контуру рахувати локальні зони ризику для здоров'я. Найважливіші локальні модифікатори: T_min уночі, UHI, LST, зелені зони, тип забудови, вік, хронічні хвороби, доступ до охолодження і перебої з електроенергією [S51-S55]."},

    {"type": "section", "title": "Таблиця змінних та індексів"},
    {"type": "table", "title": "Змінні, які треба збирати", "headers": ["Група", "Змінні", "Навіщо"], "rows": [
        ["Температура", "T2m, T_max, T_min, LST, night LST", "Виявлення хвиль, нічне відновлення, UHI"],
        ["Вологість", "RH, dew point, specific humidity", "Heat Index, Humidex, wet-bulb, evaporative cooling"],
        ["Вітер і радіація", "wind speed, wind direction, solar radiation, cloud cover", "WBGT, UTCI, outdoor exposure"],
        ["Циркуляція", "MSLP, Z500, wind fields, omega, vorticity", "Антициклон, блокування, прогноз стійкості"],
        ["Поверхня", "soil moisture, precipitation, NDVI, land cover, albedo", "Drought feedback, evapotranspiration, green-space effect"],
        ["Місто", "building density, impervious surface, LCZ, floor, AC access", "Urban heat risk and indoor exposure"],
        ["Здоров'я", "age, pregnancy, BMI, CVD, CKD, diabetes, meds, activity", "Personal vulnerability and action rules"],
        ["Повітря", "PM2.5, O3, NO2, CO, smoke products і fire products", "Compound heat та air pollution risk"],
    ]},
    {"type": "table", "title": "Індекси для сервісу", "headers": ["Індекс", "Суть та формула", "Переваги", "Недоліки та рекомендація"], "rows": [
        ["Heat Index", "Емпірична функція T і RH; 'відчувається як'", "Простий, зрозумілий, підтримується NWS", "Без сонця та вітру; додати як публічний показник"],
        ["Humidex", "T + 0.5555*(e - 10), де e - парціальний тиск водяної пари", "Зручний для вологої спеки", "Не є фізично повною моделлю; корисний як простий індекс"],
        ["Wet-bulb temperature", "Температура змоченого термометра", "Показує межу випаровувального охолодження", "Важко інтерпретувати для користувача; використовувати внутрішньо"],
        ["WBGT", "Комбінація wet-bulb, globe temperature і air temperature", "Найкраще для праці, спорту і сонця", "Потребує радіації та вітру; пріоритет для outdoor workers"],
        ["UTCI", "Терморегуляційна модель людини: T, RH, wind, radiation", "Найкращий універсальний індекс теплового стресу надворі", "Складніший розрахунок; основний шар ризику"],
        ["Apparent temperature", "T, humidity і wind у спрощеній формулі", "Простий для nowcast", "Менш повний за UTCI та WBGT"],
        ["Excess Heat Factor", "Поєднує короткочасну аномалію і акліматизацію", "Добре ловить накопичення тепла", "Потрібна якісна кліматологія; рекомендується"],
        ["HWMI та HWMId", "Магнітуда теплової хвилі відносно історичних екстремумів", "Добре для порівняння років і регіонів", "Менш прямий для медичних дій"],
        ["Tropical Night Index", "T_min >= 20 °C або локальний TN-поріг", "Ловить нічний ризик", "20 °C - не універсально; поєднати з TN_90"],
        ["WSDI", ">= 6 днів з TX > 90-й перцентиль", "Стандарт кліматичного моніторингу", "Для оперативного сервісу 6 днів може бути запізно"],
    ]},
    {"type": "callout", "title": "Рекомендований набір індексів", "text": "Для України: TX_90, TX_95, TX_99, TN_90, T_min >= 20 °C, EHF і UTCI. Для персонального застосунку: UTCI як головний outdoor index, Heat Index та Humidex як зрозумілі користувачу показники, WBGT для роботи і спорту, EHF і тривалість для накопиченого ризику."},

    {"type": "section", "title": "Вплив на здоров'я"},
    {"type": "p", "text": "Терморегуляція людини залежить від тепловіддачі через шкіру, потовиділення, серцевий викид, водно-електролітний баланс і поведінкове охолодження. За високої температури судини шкіри розширюються, кров перерозподіляється до периферії, зростає навантаження на серце, збільшується потовиділення і ризик дегідратації. Висока вологість блокує випаровування поту, а високі нічні температури зменшують відновлення [S1, S2, S47-S50]."},
    {"type": "table", "title": "Перевірка медичних тверджень", "headers": ["Твердження", "Оцінка доказів", "Коментар для застосунку"], "rows": [
        ["Зневоднення, слабкість, судоми, запаморочення", "докази сильні", "Red flags і поради щодо охолодження та рідини з винятками для HF і CKD"],
        ["Периферична вазодилатація, зміни АТ, навантаження на серце", "докази сильні", "CVD, HF, beta-blockers, antihypertensives - підвищений ризик"],
        ["Згущення крові, електролітні порушення, тромбоз", "докази помірні", "Не прогнозувати індивідуальний тромбоз; використовувати як фактор уразливості"],
        ["Інсульт, інфаркт, серцева недостатність", "докази сильні для асоціацій; механізми помірні", "Окремі risk weights для CVD, HF і hypertension"],
        ["Гостре ураження нирок і CKD", "докази сильні", "CKD, діуретики, фізична праця і дегідратація - високий ризик"],
        ["Когнітивне погіршення", "докази помірні-сильні", "Попередження для праці, водіння, іспитів, літніх людей"],
        ["Порушення сну і зниження deep sleep quality", "докази сильні для insufficient sleep; обмежені для deep sleep у популяціях", "Нічний індекс ризику і поради з охолодження кімнати"],
        ["Психічне здоров'я", "докази помірні", "Попередження для людей з psychiatric meds і тяжкими розладами"],
    ]},
    {"type": "p", "text": "Найуразливіші групи: люди віком 65+, діти, вагітні, люди з серцево-судинними хворобами, нирковою недостатністю, діабетом, ожирінням, респіраторними і психічними розладами, люди на діуретиках, антигіпертензивних, психотропних або антихолінергічних препаратах, спортсмени, працівники на відкритому повітрі, люди без кондиціонування, самотні літні люди і люди з обмеженим доступом до води [S1, S30-S39, S47]."},
    {"type": "p", "text": "Не існує одного безпечного медичного температурного порогу для всіх. Ризик стає значним при поєднанні високих T_max і T_min, вологості, тривалості, відсутності нічного охолодження, фізичного навантаження і вразливості. Тому сервіс має працювати з категоріями ризику, невизначеністю і чіткими emergency symptoms, а не з індивідуальними 'точними' прогнозами інфаркту чи інсульту."},

    {"type": "section", "title": "Аналіз наукових статей"},
    {"type": "table", "title": "Повнотекстові або легально доступні статті", "headers": ["Категорія", "Стаття", "Дизайн та вибірка", "Кількісний результат", "Практичне значення"], "rows": [
        ["смертність", "Guo et al., 2017, Environmental Health Perspectives", "400 спільнот, 18 країн і регіонів; 12 дефініцій heatwave", "Ризик смерті зростав зі збільшенням перцентильного порогу і тривалості", "Порогова модель має включати intensity і duration [S27]"],
        ["смертність", "Ballester et al., 2023, Nature Medicine", "823 регіони у 35 країнах Європи", "Оцінено близько 61 672 heat-related deaths влітку 2022", "Для Європи потрібні ранні heat-health warnings [S28]"],
        ["смертність", "Zhao et al., 2021, Lancet Planetary Health", "Глобальна multi-country модель mortality-temperature", "Близько 489 тис. heat-related deaths per year у 2000-2019", "Дає рамку burden estimation [S29]"],
        ["CVD", "Alahmad et al., 2023, Circulation", "567 міст, 27 країн, 32.15 млн CVD deaths", "Extreme heat vs MMT: IHD RR 1.07, stroke RR 1.10, HF RR 1.12", "CVD, HF і stroke history - високі weights [S30]"],
        ["CVD", "Chen et al., 2016, IJERPH", "Beijing time-series; 12 heatwave definitions", "Ефект сильніший за жорсткіших визначень і у літніх", "Локальні дефініції критично впливають на alerting [S31]"],
        ["CVD та respiratory", "Silveira et al., 2023, PLOS ONE", "Rio de Janeiro, 42 926 deaths, case-crossover та DLNM", "Heatwaves асоційовані з CVD та respiratory mortality; elderly і women вразливіші", "Враховувати вік і стать лише там, де є медична користь [S32]"],
        ["нирки", "Lee et al., 2019, J Prev Med Public Health", "Systematic review and meta-analysis kidney morbidity", "Високі температури пов'язані з kidney morbidity", "CKD і дегідратація - окремий high-risk flag [S33]"],
        ["нирки", "Remigio et al., 2019, JAMA Network Open", "Пацієнти з ESRD; госпіталізації та смертність під час extreme heat", "ESRD група має підвищений ризик під час спеки", "Рекомендації щодо води тільки з обмеженнями лікаря [S34]"],
        ["нирки", "Chapman et al., 2020, Journal of Applied Physiology", "13 здорових дорослих, 2 год праці у ~39.7 °C", "Hyperthermia і dehydration підвищували AKI biomarkers", "WBGT, активність і доступ до води важливі [S35]"],
        ["мозок", "Cedeño Laurent et al., 2018, PLOS Medicine", "44 студенти, будівлі з AC і без AC", "Під час хвилі спеки когнітивні тести були гірші у non-AC групі", "Indoor heat exposure треба врахувати [S36]"],
        ["сон", "Obradovich et al., 2017, Science Advances", "765 тис. респондентів США", "Нічні температурні аномалії збільшували insufficient sleep", "T_min і tropical nights - окремий health trigger [S37]"],
        ["мозок", "Shibasaki et al., 2017, Scientific Reports", "Контрольована пасивна гіпертермія з EEG і P300", "Підвищення core temperature пригнічувало P300", "Для high-risk activity варто попереджати про когнітивне навантаження [S38]"],
        ["вагітність", "Chersich et al., 2020, BMJ", "70 досліджень, 27 країн", "Preterm birth OR 1.05 на 1 °C і OR 1.16 під час heatwaves", "Вагітність - доказовий vulnerability flag [S39]"],
        ["моделювання", "Cho et al., 2026, npj Climate and Atmospheric Science", "DL land-atmosphere coupled model, Northern Hemisphere", "Multi-step land-atmosphere coupling покращив heatwave forecast accuracy на 5.9-11.2%", "Soil moisture і land state треба включити [S40]"],
        ["прогноз DL", "Lam et al., 2023, Science", "GraphCast, graph neural network, ERA5, 0.25° grid", "10-денні прогнози, 227 змінних, 6-годинний крок; кращі за HRES на більшості цілей", "Підходить як reference architecture для просторово-часового forecast layer [S57]"],
        ["прогноз DL", "Bi et al., 2023, Nature", "Pangu-Weather, 3D Earth-specific Transformer, 39 років ERA5", "Автори показали сильну детерміновану якість прогнозу і корисність для екстремальної погоди", "Підтримує 3D atmospheric encoder для антициклонів і Z500 patterns [S58]"],
        ["ймовірнісний DL", "Price et al., 2025, Nature", "GenCast, diffusion model, 15-денний ensemble forecast", "0.25°, понад 80 змінних, 8 хв на один forecast; краща skill за ENS на 97.2% цілей", "Для heat-health alerts потрібні probability maps, не один deterministic run [S60]"],
        ["операційний AI-прогноз", "ECMWF AIFS, 2025-2026", "AIFS Single та AIFS ENS, 0.25°, 6-годинний крок, 15 днів", "Операційний з 2025 року; open data доступні після production", "MVP може споживати AIFS замість тренування global model з нуля [S56, S62]"],
        ["міський DL", "Zhu et al., 2024, ISPRS JPRS", "LCZ mapping, ResNet50, multi-source fusion, Landsat і urban morphology", "Average overall accuracy >94% у 18 містах Китаю", "Для Києва потрібен transfer learning LCZ layer [S63]"],
        ["health prediction", "Kuo et al., 2025, IJMI", "820 ED пацієнтів з heat-related illness, ML і MLP", "AUC 0.825-0.991; LightGBM був найкращий, важливі SpO2 і GCS", "Для consumer app це доказ потенціалу ML, але не готова персональна модель [S64]"],
        ["моделювання", "Weirich-Benet et al., 2023, Artificial Intelligence for the Earth Systems", "Central Europe, linear model і RF, 1-6 weeks", "ML перевищував persistence і climatology та конкурував з ECMWF hindcast >2 тижнів", "Subseasonal layer після MVP [S41]"],
        ["супутники", "Hou et al., 2023, International Journal of Applied Earth Observation and Geoinformation", "Global 2018 heatwaves за Aqua LST", "Satellite LST допомагає просторово характеризувати heatwaves", "LST map layer для сервісу [S42]"],
        ["супутники", "Ghatak et al., 2017, Scientific Reports", "Indian 2015 heatwave: stations, reanalysis, satellite і land models", "Сухість ґрунту та vegetation stress підтримували local heating", "Поєднувати LST, soil moisture і reanalysis [S43]"],
        ["супутники та UHI", "Hidalgo Garcia et al., 2022, Sustainability", "Sentinel-3, urban thermal effects during heatwaves", "Remote sensing виявляє просторово-часові UHI effects", "Sentinel-3 придатний для міських карт [S44]"],
    ]},

    {"type": "section", "title": "Архітектура застосунку"},
    {"type": "p", "text": "MVP має бути геопросторовим конвеєром, а не лише мобільною формою. Нижній шар збирає прогнози, реаналізи і супутникові продукти. Середній шар нормалізує їх у спільну сітку та тайли, рахує пороги й індекси. Верхній шар поєднує теплову небезпеку з профілем користувача, генерує пояснення і надсилає сповіщення."},
    {"type": "table", "title": "Технічний стек MVP", "headers": ["Компонент", "Рекомендація", "Причина"], "rows": [
        ["API backend", "Python + FastAPI", "Швидка інтеграція з науковим Python"],
        ["База", "PostgreSQL + PostGIS + TimescaleDB", "Геометрія, точки користувачів, часові ряди"],
        ["Растри", "Cloud Optimized GeoTIFF, NetCDF, Zarr", "Стандарти для супутників, реаналізів і великих масивів"],
        ["Обробка", "xarray, rioxarray, rasterio, GDAL, Dask", "Сіткові дані, lazy loading, chunking"],
        ["Deep learning", "PyTorch, PyTorch Lightning, xarray, Zarr, Dask, MLflow", "HeatWaveNet, UrbanNet і DeepRisk як основні model layers"],
        ["Model serving", "ONNX Runtime, TorchServe або FastAPI worker", "Швидкий inference для карт, профілю і сповіщень"],
        ["Черги", "Celery + Redis або RQ", "Періодичне оновлення прогнозів і тайлів"],
        ["Фронтенд", "React або Next.js з MapLibre чи Leaflet", "Карта ризику, профіль, пояснення"],
        ["Інфраструктура", "Docker, object storage, scheduled jobs", "Відтворюваність і масштабування"],
    ]},
    {"type": "p", "text": "Оновлення даних: AIFS ENS, IFS, GFS та ICON 4 рази на добу; ERA5-Land для кліматології раз на день або при ретропроцесінгу; Sentinel-3, MODIS і VIIRS при надходженні NRT; Landsat раз на 8-16 днів для міських UHI layers; Sentinel-5P і CAMS daily або near-real-time для повітря. Великі растри зберігати як COG і Zarr з chunking, будувати XYZ tiles та vector tiles для карти і кешувати лише потрібні часові шари."},
    {"type": "p", "text": "Просторова інтерполяція: для MVP достатньо bilinear або nearest interpolation на регулярних сітках і neural bias correction за станціями. Для міста - neural downscaling через land cover, NDVI, impervious surface, elevation, LCZ і локальні станції. Валідація прогнозу: hindcast останніх 5-10 років, Brier score для exceedance probability, MAE та RMSE для T_max і T_min, CRPS для ensemble maps і reliability diagrams для категорій ризику."},

    {"type": "section", "title": "Персональна модель ризику"},
    {"type": "p", "text": "Основна продуктова модель може бути deep-learning-first: мультимодальна neural risk model, яка окремо кодує погоду, міське середовище, профіль людини і фактичну експозицію. Вона не повинна обіцяти діагноз або точну індивідуальну ймовірність без клінічної валідації. Просту статистику варто залишити тільки як baseline для перевірки, а не як головну модель продукту."},
    {"type": "equation", "text": "DeepRisk:\n  weather_embedding = WeatherEncoder(T_max, T_min, UTCI, WBGT, EHF, AQI, forecast_ensemble)\n  urban_embedding = UrbanEncoder(LST, LCZ, NDVI, building_density, floor, cooling_access)\n  profile_embedding = ProfileEncoder(age, pregnancy, CVD, CKD, diabetes, meds, activity)\n  output = RiskHead(weather_embedding, urban_embedding, profile_embedding, exposure_context)"},
    {"type": "table", "title": "Нейронні блоки DeepRisk", "headers": ["Блок", "Роль", "Приклади факторів"], "rows": [
        ["WeatherEncoder", "стискає часовий ряд і ensemble forecast у вектор небезпеки", "T_max percentile, T_min percentile, UTCI, Heat Index, WBGT, EHF, тривалість, AQI"],
        ["UrbanEncoder", "враховує мікроклімат місця проживання", "LST, LCZ, NDVI, поверх, щільна забудова, green space, UHI"],
        ["ProfileEncoder", "кодує медичну вразливість без діагностичних claims", "65+, дитина, вагітність, CVD, HF, hypertension, diabetes, CKD, COPD, asthma, obesity, ліки"],
        ["ExposureEncoder", "оцінює контакт людини зі спекою", "робота надворі, спорт, сонце, транспорт, ніч без охолодження"],
        ["ProtectionEncoder", "знижує ризик, якщо є реальні захисні ресурси", "кондиціонер, прохолодне приміщення, вода, соціальна підтримка, акліматизація"],
        ["RiskHead", "видає категорію, діапазон невизначеності і top explanations", "низький, середній, високий, критичний"],
    ]},
    {"type": "table", "title": "Категорії ризику", "headers": ["Категорія", "Правило MVP", "Дія"], "rows": [
        ["Низький", "модель і safety guardrails не бачать істотної небезпеки", "Показати прогноз і базові поради"],
        ["Середній", "модель бачить помірну теплову небезпеку або тропічну ніч для вразливої людини", "Обмежити пік спеки, нагадати про охолодження"],
        ["Високий", "модель бачить сильну спеку плюс CVD, CKD, diabetes, pregnancy, ліки або високу експозицію", "Активні сповіщення, план води, охолодження та перевірки"],
        ["Критичний", "extreme UTCI або WBGT, швидке зростання ризику, або emergency symptoms", "Порада негайно охолоджуватися і звернутися по медичну допомогу"],
    ]},
    {"type": "p", "text": "Калібрування: локальні дані швидкої допомоги, госпіталізацій, смертності, звернень до сімейних лікарів і синоптичних спостережень. Валідація: temporal split, spatial split, calibration curve, Brier score, AUROC, PR-AUC, subgroup performance і decision curve analysis. Невизначеність: показувати діапазон ризику або confidence label, а не точну цифру без пояснення. Для production потрібні deep ensembles, conformal prediction і клінічний review."},

    {"type": "section", "title": "Рекомендації користувачам"},
    {"type": "p", "text": "Рекомендації мають бути rule-based, медично обережними і прив'язаними до профілю. Не можна давати універсальну норму води для людей із серцевою недостатністю, хронічною хворобою нирок або обмеженням рідини. Ліки не припиняти самостійно; користувач має отримати підказку обговорити план спеки з лікарем [S47-S50]."},
    {"type": "table", "title": "Рекомендації за рівнем ризику", "headers": ["Ризик", "Рекомендації"], "rows": [
        ["Низький", "Слідкувати за прогнозом; пити регулярно; уникати надмірного алкоголю; планувати активність на ранок або вечір."],
        ["Середній", "Уникати перебування на сонці у пікові години; закривати штори вдень і провітрювати вночі; перевірити дітей, літніх і домашній запас води та ліків."],
        ["Високий", "Скоротити фізичні навантаження; провести частину дня у прохолодному місці; мати план на випадок відключення електроенергії; перевіряти симптоми теплового виснаження."],
        ["Критичний", "Активне охолодження, супровід, відміна outdoor activity. При сплутаності, непритомності, судомах, гарячій сухій шкірі, швидкому пульсі або диханні, або відсутності поліпшення - термінова медична допомога."],
    ]},
    {"type": "p", "text": "Вентилятор корисний не завжди. За дуже високої температури він може просто ганяти гаряче повітря і не замінює охолодження. WHO попереджає не покладатися на вентилятор як основний спосіб охолодження вище 40 °C; NHS описує користь вентиляторів переважно при нижчих indoor temperatures. Для застосунку треба показувати це як умовну пораду: 'вентилятор, волога шкіра та провітрювання, якщо кімната не перегріта; шукайте прохолодне місце, якщо indoor heat небезпечна' [S2, S49]."},

    {"type": "section", "title": "Український контекст"},
    {"type": "p", "text": "Для України потрібні регіональні пороги. Південь і південний схід мають вищі абсолютні літні температури і більшу посушливість; центр і схід мають ризик тривалих континентальних хвиль; захід і Карпати мають нижчі абсолютні пороги, але відносні екстремуми все одно важливі. Великі міста - Київ, Харків, Дніпро, Одеса, Запоріжжя, Львів - потребують окремого UHI-шару через забудову, зелені зони, водойми і нічне накопичення тепла [S45, S46]."},
    {"type": "p", "text": "Відкритий веб Укргідрометцентру надає прогнози і попередження, але повноцінний відкритий історичний API для сирих станційних даних не підтверджений. Для MVP можна використати ERA5-Land як кліматологічну базу, ECMWF, GFS та ICON для прогнозу, Sentinel-3, MODIS, VIIRS і Landsat для LST та UHI, а українські станційні дані підключати через офіційні угоди або дозволені відкриті канали [S17-S26, S46]."},
    {"type": "p", "text": "Воєнні умови змінюють exposure: перебої з електроенергією, пошкоджена водна інфраструктура, укриття без вентиляції, вимушене переміщення, переповнені житла, обмежений доступ до медицини і ліків. Це не метеорологічні фактори, але вони мають входити у персональний ризик як protection modifiers та exposure modifiers."},

    {"type": "section", "title": "Обмеження та етичні ризики"},
    {"type": "p", "text": "Найбільше обмеження - перенесення популяційних асоціацій на конкретну людину. Навіть якщо RR підвищений, це не означає точний індивідуальний прогноз. Тому застосунок має чітко казати: 'це оцінка ризику і рекомендації з безпеки, а не медичний діагноз'. Для медичних claims потрібні клінічна експертиза, локальна валідація і регулярний review."},
    {"type": "p", "text": "Етичні вимоги: мінімізація медичних даних, opt-in для геолокації, можливість грубого місця замість точної адреси, локальна обробка профілю там, де можливо, пояснюваність категорій, accessibility, низький поріг для emergency advice, захист від alert fatigue, відсутність дискримінації за віком, вагою та статтю. Особливо обережно треба поводитися з даними вагітності, хвороб, ліків і місця проживання."},

    {"type": "section", "title": "План реалізації MVP"},
    {"type": "table", "title": "Етапи", "headers": ["Етап", "Результат"], "rows": [
        ["1. Кліматологія", "Завантажити ERA5-Land 1991-2020, обчислити TX_90, TX_95, TX_99 і TN_90 для України"],
        ["2. Оперативний прогноз", "Підключити ECMWF AIFS ENS, ECMWF Open Data, GFS та ICON, рахувати exceedance probability на 1-15 днів"],
        ["3. Індекси", "Реалізувати Heat Index, Humidex, UTCI та WBGT approximation, EHF і tropical nights"],
        ["4. Deep learning pilot", "Навчити HeatWaveNet для локальної корекції T_max, T_min, UTCI і маски хвилі"],
        ["5. Карта", "COG і Zarr pipeline, тайли ризику, часова анімація теплової небезпеки"],
        ["6. Профіль", "Мінімальна анкета: вік, вагітність, CVD, CKD, diabetes, ліки, активність, AC та water access"],
        ["7. DeepRisk", "Мультимодальна neural risk model з safety guardrails і поясненням top factors"],
        ["8. Рекомендації", "Rule engine з джерел WHO, CDC та NHS, emergency red flags, обережність щодо води і ліків"],
        ["9. Українські міста", "Landsat, Sentinel-3 і MODIS UHI layers для Києва, Харкова, Дніпра, Одеси, Львова"],
        ["10. Валідація", "Hindcast, станційна перевірка, CRPS, calibration, user testing, медичний review"],
    ]},

    {"type": "section", "title": "Список джерел"},
]


def tex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def tex_markup(text: str) -> str:
    rendered = tex_escape(text)
    for raw, _pdf, tex in VARIABLE_MARKUP:
        rendered = rendered.replace(tex_escape(raw), tex)
    return rendered


def pdf_markup(text: str) -> str:
    rendered = escape(text)
    for raw, pdf, _tex in VARIABLE_MARKUP:
        rendered = rendered.replace(escape(raw), pdf)
    return rendered


def table_to_tex(title: str, headers: list[str], rows: list[list[str]]) -> str:
    colspec = "p{0.22\\textwidth}" + "p{0.24\\textwidth}" * (len(headers) - 1)
    lines = [
        r"\begin{longtable}{" + colspec + "}",
        r"\caption{" + tex_markup(title) + r"}\\",
        r"\toprule",
        " & ".join(tex_markup(h) for h in headers) + r"\\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        " & ".join(tex_markup(h) for h in headers) + r"\\",
        r"\midrule",
        r"\endhead",
    ]
    for row in rows:
        lines.append(" & ".join(tex_markup(c) for c in row) + r"\\")
    lines.extend([r"\bottomrule", r"\end{longtable}"])
    return "\n".join(lines)


def render_tex() -> str:
    parts = [
        r"\documentclass[12pt,a4paper]{article}",
        r"\usepackage{fontspec}",
        r"\usepackage{polyglossia}",
        r"\setmainlanguage{ukrainian}",
        r"\setmainfont{Times New Roman}",
        r"\usepackage{geometry}",
        r"\geometry{margin=2.2cm}",
        r"\usepackage{booktabs,longtable,array}",
        r"\usepackage{xcolor}",
        r"\usepackage{hyperref}",
        r"\usepackage{enumitem}",
        r"\hypersetup{colorlinks=true,linkcolor=blue,urlcolor=blue,citecolor=blue}",
        r"\setlist{nosep}",
        r"\title{" + tex_escape(TITLE) + r"}",
        r"\author{" + tex_escape(SUBTITLE) + r"}",
        r"\date{" + tex_escape(DATE) + r"}",
        r"\begin{document}",
        r"\maketitle",
        r"\tableofcontents",
        r"\newpage",
    ]

    for block in BLOCKS:
        kind = block["type"]
        if kind == "toc":
            continue
        if kind == "section":
            parts.append(r"\section{" + tex_markup(block["title"]) + "}")
        elif kind == "p":
            parts.append(tex_markup(block["text"]) + "\n")
        elif kind == "quote":
            parts.append(r"\begin{quote}" + tex_markup(block["text"]) + r"\end{quote}")
        elif kind == "callout":
            parts.append(r"\subsection*{" + tex_markup(block["title"]) + "}")
            parts.append(tex_markup(block["text"]) + "\n")
        elif kind == "equation":
            parts.append(r"\begin{verbatim}" + "\n" + block["text"] + "\n" + r"\end{verbatim}")
        elif kind == "table":
            parts.append(table_to_tex(block["title"], block["headers"], block["rows"]))

    parts.append(r"\begin{thebibliography}{99}")
    for src in SOURCES:
        label = src.key.replace("S", "")
        doi = f", DOI: {src.doi}" if src.doi else ""
        parts.append(r"\bibitem{" + src.key + "} " + tex_escape(f"{src.title}. {src.kind}{doi}. ") + r"\url{" + src.url + "}")
    parts.extend([r"\end{thebibliography}", r"\end{document}", ""])
    return "\n\n".join(parts)


def register_fonts() -> tuple[str, str, str, str]:
    font_dir = Path("/System/Library/Fonts/Supplemental")
    regular = font_dir / "Times New Roman.ttf"
    bold = font_dir / "Times New Roman Bold.ttf"
    italic = font_dir / "Times New Roman Italic.ttf"
    bold_italic = font_dir / "Times New Roman Bold Italic.ttf"

    pdfmetrics.registerFont(TTFont("TNR", str(regular)))
    pdfmetrics.registerFont(TTFont("TNR-Bold", str(bold)))
    pdfmetrics.registerFont(TTFont("TNR-Italic", str(italic)))
    pdfmetrics.registerFont(TTFont("TNR-BoldItalic", str(bold_italic)))
    pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic", boldItalic="TNR-BoldItalic")
    return "TNR", "TNR-Bold", "TNR-Italic", "TNR-BoldItalic"


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("TitleCustom", parent=base["Title"], fontName="TNR-Bold", fontSize=22, leading=27, alignment=TA_CENTER, spaceAfter=16, textColor=colors.HexColor("#111827")),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontName="TNR", fontSize=12.5, leading=17, alignment=TA_CENTER, spaceAfter=8, textColor=colors.HexColor("#374151")),
        "date": ParagraphStyle("Date", parent=base["Normal"], fontName="TNR-Italic", fontSize=10.5, leading=14, alignment=TA_CENTER, spaceAfter=20, textColor=colors.HexColor("#4b5563")),
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontName="TNR-Bold", fontSize=15.5, leading=20, spaceBefore=14, spaceAfter=7, textColor=colors.HexColor("#111827"), keepWithNext=True),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName="TNR-Bold", fontSize=12.2, leading=16, spaceBefore=10, spaceAfter=5, textColor=colors.HexColor("#1f2937"), keepWithNext=True),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName="TNR", fontSize=10.1, leading=14.2, spaceAfter=7, alignment=TA_JUSTIFY),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName="TNR", fontSize=8.0, leading=10, spaceAfter=4, alignment=TA_LEFT),
        "bullet": ParagraphStyle("Bullet", parent=base["BodyText"], fontName="TNR", fontSize=10, leading=13.5, leftIndent=14, firstLineIndent=-9, spaceAfter=3),
        "quote": ParagraphStyle("Quote", parent=base["BodyText"], fontName="TNR-Italic", fontSize=10, leading=14, leftIndent=16, rightIndent=12, spaceBefore=5, spaceAfter=8, borderColor=colors.HexColor("#d1d5db"), borderWidth=0.7, borderPadding=7, backColor=colors.HexColor("#f9fafb")),
        "callout_title": ParagraphStyle("CalloutTitle", parent=base["BodyText"], fontName="TNR-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#111827"), spaceAfter=2),
        "callout": ParagraphStyle("Callout", parent=base["BodyText"], fontName="TNR", fontSize=9.8, leading=13.5, leftIndent=8, rightIndent=8, spaceAfter=7, borderColor=colors.HexColor("#9ca3af"), borderWidth=0.6, borderPadding=8, backColor=colors.HexColor("#f8fafc")),
        "equation": ParagraphStyle("Equation", parent=base["Code"], fontName="Courier", fontSize=8.7, leading=11, leftIndent=10, rightIndent=10, spaceBefore=4, spaceAfter=8, borderColor=colors.HexColor("#e5e7eb"), borderWidth=0.5, borderPadding=7, backColor=colors.HexColor("#fbfbfb"), wordWrap="CJK"),
        "toc": ParagraphStyle("Toc", parent=base["BodyText"], fontName="TNR", fontSize=10.5, leading=15, leftIndent=12, spaceAfter=3),
    }


def para(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(pdf_markup(text), style)


def clean_url_for_pdf(url: str) -> str:
    return re.sub(r"([/?&=_#.-])", r"\1 ", url)


def make_table(title: str, headers: list[str], rows: list[list[str]], styles: dict[str, ParagraphStyle]) -> list:
    story: list = [Paragraph(pdf_markup(title), styles["h2"])]
    col_count = len(headers)
    available_width = A4[0] - 4.3 * cm
    if col_count == 2:
        widths = [0.22 * available_width, 0.78 * available_width]
    elif col_count == 3:
        widths = [0.18 * available_width, 0.37 * available_width, 0.45 * available_width]
    elif col_count == 4:
        widths = [0.19 * available_width, 0.26 * available_width, 0.27 * available_width, 0.28 * available_width]
    elif col_count == 5:
        widths = [0.13 * available_width, 0.16 * available_width, 0.24 * available_width, 0.24 * available_width, 0.23 * available_width]
    else:
        widths = [available_width / col_count] * col_count

    header_cells = [Paragraph(pdf_markup(h), ParagraphStyle("TH", parent=styles["small"], fontName="TNR-Bold", textColor=colors.white)) for h in headers]
    body_style = ParagraphStyle("TD", parent=styles["small"], fontSize=7.3 if col_count >= 5 else 8.0, leading=9.2 if col_count >= 5 else 10.0)
    data = [header_cells]
    for row in rows:
        data.append([Paragraph(pdf_markup(str(cell)), body_style) for cell in row])

    table = LongTable(data, colWidths=widths, repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "TNR-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([table, Spacer(1, 7)])
    return story


def build_pdf() -> None:
    register_fonts()
    styles = make_styles()

    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=2.15 * cm,
        rightMargin=2.15 * cm,
        topMargin=2.1 * cm,
        bottomMargin=1.8 * cm,
        title=TITLE,
        author="Codex",
        subject=SUBTITLE,
    )

    story: list = [
        Spacer(1, 3.2 * cm),
        Paragraph(escape(TITLE), styles["title"]),
        Paragraph(escape(SUBTITLE), styles["subtitle"]),
        Paragraph(escape(DATE), styles["date"]),
        Spacer(1, 1.2 * cm),
        Table(
            [[Paragraph(escape("Документ оформлено в академічному LaTeX-стилі: структуровані розділи, формули, довгі таблиці, нумерація сторінок і список джерел. Окремо збережено .tex-джерело для подальшої роботи з документом."), styles["body"])]],
            colWidths=[A4[0] - 4.3 * cm],
            style=TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#9ca3af")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]),
        ),
        PageBreak(),
    ]

    for block in BLOCKS:
        kind = block["type"]
        if kind == "toc":
            story.append(Paragraph("Зміст", styles["h1"]))
            for idx, item in enumerate(block["items"], start=1):
                story.append(Paragraph(f"{idx}. {pdf_markup(item)}", styles["toc"]))
            story.append(PageBreak())
        elif kind == "section":
            story.append(Paragraph(pdf_markup(block["title"]), styles["h1"]))
        elif kind == "p":
            story.append(para(block["text"], styles["body"]))
        elif kind == "quote":
            story.append(Paragraph(pdf_markup(block["text"]), styles["quote"]))
        elif kind == "callout":
            content = f"<b>{pdf_markup(block['title'])}</b><br/>{pdf_markup(block['text'])}"
            story.append(KeepTogether([Paragraph(content, styles["callout"])]))
        elif kind == "equation":
            story.append(Preformatted(block["text"], styles["equation"]))
        elif kind == "table":
            story.extend(make_table(block["title"], block["headers"], block["rows"], styles))

    src_header = [Paragraph("ID", ParagraphStyle("SH", parent=styles["small"], fontName="TNR-Bold", textColor=colors.white)),
                  Paragraph("Джерело", ParagraphStyle("SH2", parent=styles["small"], fontName="TNR-Bold", textColor=colors.white))]
    src_rows = [src_header]
    src_style = ParagraphStyle("SourceCell", parent=styles["small"], fontSize=7.4, leading=9.4, wordWrap="CJK")
    for src in SOURCES:
        doi = f"; DOI: {src.doi}" if src.doi else ""
        text = f"{src.title}. {src.kind}{doi}. URL: {clean_url_for_pdf(src.url)}"
        src_rows.append([Paragraph(src.key, src_style), Paragraph(escape(text), src_style)])

    available_width = A4[0] - 4.3 * cm
    src_table = LongTable(src_rows, colWidths=[1.2 * cm, available_width - 1.2 * cm], repeatRows=1, splitByRow=1)
    src_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(src_table)

    def draw_page(canvas, document):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, width, height, stroke=0, fill=1)
        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.setLineWidth(0.4)
        canvas.line(document.leftMargin, height - 1.55 * cm, width - document.rightMargin, height - 1.55 * cm)
        canvas.setFont("TNR", 8)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(document.leftMargin, 1.05 * cm, "Теплові хвилі: науково-технічний brief")
        canvas.drawRightString(width - document.rightMargin, 1.05 * cm, f"Стор. {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)


def assert_no_bad_dashes(text: str) -> None:
    bad = {
        "\u2013": "en dash",
        "\u2014": "em dash",
        "\u2011": "non-breaking hyphen",
    }
    found = [name for ch, name in bad.items() if ch in text]
    if found:
        raise ValueError(f"Found forbidden dash characters: {', '.join(found)}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tex = render_tex()
    all_text = tex + "\n" + "\n".join(str(block) for block in BLOCKS)
    assert_no_bad_dashes(all_text)
    TEX_PATH.write_text(tex, encoding="utf-8")
    build_pdf()
    print(PDF_PATH)
    print(TEX_PATH)


if __name__ == "__main__":
    main()
