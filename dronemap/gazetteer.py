"""Place-name gazetteer for Ukrainian air-raid monitoring messages.

Each row: oblast ; key ; English name ; lat ; lon ; kind ; tokens

kind:  R = region (oblast)   C = major city   T = town   D = city district
       F = foreign launch area   W = water body / landmark area

tokens (comma separated, matched on lower-cased, normalised text):
  ~   -> up to 3 more word characters (case endings: Полтав~ = Полтава/Полтаву/Полтавою)
  *   -> any number of word characters
  ' ' -> one or more spaces
  '   -> optional apostrophe
  -   -> optional hyphen/space
  /…  -> raw regular expression (must start with at least 3 literal letters)
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from dataclasses import dataclass, field

DATA = r"""
# ---------------------------------------------------------------- regions
vinnytsia; obl_vinnytsia; Vinnytsia region; 48.95; 28.75; R; вінниччин~,вінничин~,вінницьк~ обл*,винниччин~,винничин~,винницк~ обл*
volyn; obl_volyn; Volyn region; 51.20; 25.00; R; волин~,волинськ~ обл*,волын~,волынск~ обл*
dnipro; obl_dnipro; Dnipropetrovsk region; 48.35; 34.95; R; дніпропетровщин~,дніпровщин~,січеславщин~,дніпропетровськ~ обл*,дніпровськ~ обл*,днепропетровщин~,днепропетровск~ обл*,днепровщин~
donetsk; obl_donetsk; Donetsk region; 48.50; 37.70; R; днр,донеччин~,донецьк~ обл*,донетчин~,донецк~ обл*,донбас~
zhytomyr; obl_zhytomyr; Zhytomyr region; 50.50; 28.40; R; житомирщин~,житомирськ~ обл*,житомирск~ обл*
zakarpattia; obl_zakarpattia; Zakarpattia region; 48.40; 23.30; R; закарпатт~,закарпатськ~ обл*,закарпать~,закарпатск~ обл*
zaporizhzhia; obl_zaporizhzhia; Zaporizhzhia region; 47.70; 35.60; R; запоріжчин~,запорізьк~ обл*,запорожск~ обл*
ivano_frankivsk; obl_if; Ivano-Frankivsk region; 48.75; 24.60; R; івано-франківщин~,франківщин~,прикарпатт~,/івано-?\s?франківськ\w*\s+обл\w*,/ивано-?\s?франковск\w*\s+обл\w*,прикарпать~
kyiv; obl_kyiv; Kyiv region; 50.30; 30.85; R; київщин~,київськ~ обл*,киевщин~,киевск~ обл*
kirovohrad; obl_kirovohrad; Kirovohrad region; 48.45; 32.00; R; кіровоградщин~,кропивниччин~,кіровоградськ~ обл*,кировоградщин~,кировоградск~ обл*
luhansk; obl_luhansk; Luhansk region; 48.90; 39.00; R; лнр,луганщин~,луганськ~ обл*,луганск~ обл*
lviv; obl_lviv; Lviv region; 49.80; 24.00; R; львівщин~,львівськ~ обл*,львовщин~,львовск~ обл*
mykolaiv; obl_mykolaiv; Mykolaiv region; 47.35; 31.80; R; миколаївщин~,миколаївськ~ обл*,николаевщин~,николаевск~ обл*
odesa; obl_odesa; Odesa region; 46.90; 30.20; R; одещин~,одеськ~ обл*,одесщин~,одесск~ обл*
poltava; obl_poltava; Poltava region; 49.60; 33.90; R; полтавщин~,полтавськ~ обл*,полтавск~ обл*
rivne; obl_rivne; Rivne region; 51.00; 26.30; R; рівненщин~,рівненськ~ обл*,ровенщин~,ровенск~ обл*
sumy; obl_sumy; Sumy region; 51.00; 34.20; R; сумщин~,сумськ~ обл*,сумск~ обл*
ternopil; obl_ternopil; Ternopil region; 49.40; 25.60; R; тернопільщин~,тернопільськ~ обл*,тернопольщин~,тернопольск~ обл*
kharkiv; obl_kharkiv; Kharkiv region; 49.60; 36.50; R; харківщин~,харківськ~ обл*,харьковщин~,харьковск~ обл*,слобожанщин~
kherson; obl_kherson; Kherson region; 46.85; 33.10; R; херсонщин~,херсонськ~ обл*,херсонск~ обл*
khmelnytskyi; obl_khmelnytskyi; Khmelnytskyi region; 49.40; 26.90; R; хмельниччин~,хмельничин~,хмельницьк~ обл*,хмельницк~ обл*
cherkasy; obl_cherkasy; Cherkasy region; 49.15; 31.50; R; черкащин~,черкаськ~ обл*,черкасщин~,черкасск~ обл*
chernivtsi; obl_chernivtsi; Chernivtsi region; 48.30; 25.90; R; буковин~,чернівеччин~,чернівецьк~ обл*,черновицк~ обл*
chernihiv; obl_chernihiv; Chernihiv region; 51.35; 32.00; R; чернігівщин~,чернігівськ~ обл*,черниговщин~,черниговск~ обл*
crimea; obl_crimea; Crimea; 45.30; 34.20; R; крим~,крым~
# ---------------------------------------------------------------- Kyiv city
kyiv_city; kyiv; Kyiv; 50.450; 30.523; C; київ,києв~,киев~,столиц~
kyiv_city; kyiv_obolon; Obolon (Kyiv); 50.51; 30.50; D; оболон~,оболонь
kyiv_city; kyiv_troieshchyna; Troieshchyna (Kyiv); 50.51; 30.61; D; троєщин~,троещин~
kyiv_city; kyiv_darnytsia; Darnytsia (Kyiv); 50.43; 30.63; D; дарниц~
kyiv_city; kyiv_sviatoshyn; Sviatoshyn (Kyiv); 50.46; 30.36; D; святошин~
kyiv_city; kyiv_borshchahivka; Borshchahivka (Kyiv); 50.42; 30.36; D; борщагівк~,борщагівц~,борщаговк~
kyiv_city; kyiv_holosiiv; Holosiiv (Kyiv); 50.38; 30.50; D; голосіїв~,голосієв~,голосеев~
kyiv_city; kyiv_vynohradar; Vynohradar (Kyiv); 50.51; 30.43; D; виноградар~
kyiv_city; kyiv_pozniaky; Pozniaky (Kyiv); 50.40; 30.64; D; позняк~
kyiv_city; kyiv_osokorky; Osokorky (Kyiv); 50.39; 30.62; D; осокорк~
kyiv_city; kyiv_teremky; Teremky (Kyiv); 50.37; 30.45; D; теремк~,теремок
kyiv_city; kyiv_zhuliany; Zhuliany (Kyiv); 50.40; 30.45; D; жулян~
kyiv_city; kyiv_pechersk; Pechersk (Kyiv); 50.43; 30.55; D; печерськ~,печерск~
kyiv_city; kyiv_solomianka; Solomianka (Kyiv); 50.43; 30.47; D; солом'янк~
# ---------------------------------------------------------------- Kyiv region
kyiv; bila_tserkva; Bila Tserkva; 49.809; 30.111; T; /біл(?:а|ої|у|ій|ою)\s+церк\w*,/бел(?:ая|ой|ую)\s+церк\w*
kyiv; brovary; Brovary; 50.511; 30.790; T; бровар~
kyiv; boryspil; Boryspil; 50.353; 30.955; T; бориспіл~,бориспол~
kyiv; fastiv; Fastiv; 50.077; 29.918; T; фастів,фастов~
kyiv; vasylkiv; Vasylkiv; 50.178; 30.321; T; васильків,васильков~
kyiv; obukhiv; Obukhiv; 50.107; 30.618; T; обухів,обухов~
kyiv; irpin; Irpin; 50.522; 30.250; T; ірпін~,ірпен~,ирпен~
kyiv; bucha; Bucha; 50.548; 30.212; T; буча,бучу,бучі,бучею,буче
kyiv; hostomel; Hostomel; 50.570; 30.265; T; гостомел~,гостомель
kyiv; vyshhorod; Vyshhorod; 50.585; 30.488; T; вишгород~,вышгород~
kyiv; pereiaslav; Pereiaslav; 50.065; 31.445; T; переяслав~
kyiv; yahotyn; Yahotyn; 50.279; 31.765; T; яготин~
kyiv; baryshivka; Baryshivka; 50.364; 31.321; T; баришівк~,баришівц~
kyiv; kaharlyk; Kaharlyk; 49.858; 30.826; T; кагарлик~
kyiv; myronivka; Myronivka; 49.660; 31.010; T; миронівк~,миронівц~,мироновк~
kyiv; uzyn; Uzyn; 49.826; 30.414; T; узин~
kyiv; makariv; Makariv; 50.464; 29.811; T; макарів,макарова,макарові
kyiv; borodianka; Borodianka; 50.645; 29.920; T; бородянк~,бородянц~
kyiv; ivankiv; Ivankiv; 50.935; 29.892; T; іванків,іванкова,іванкові,иванков~
kyiv; slavutych; Slavutych; 51.521; 30.756; T; славутич~
kyiv; tarashcha; Tarashcha; 49.556; 30.505; T; таращ~
kyiv; rzhyshchiv; Rzhyshchiv; 49.969; 31.042; T; ржищів,ржищев~
kyiv; bohuslav; Bohuslav; 49.546; 30.874; T; богуслав~
kyiv; skvyra; Skvyra; 49.733; 29.664; T; сквир~
kyiv; dymer; Dymer; 50.786; 30.300; T; димер,димера,димері,димером
kyiv; velyka_dymerka; Velyka Dymerka; 50.590; 30.910; T; /велик\w*\s+димерк\w*
kyiv; chornobyl; Chornobyl; 51.389; 30.099; T; чорнобил~,чернобыл~,чаес
kyiv; kyiv_reservoir; Kyiv Reservoir; 50.85; 30.45; W; /київськ\w*\s+водосховищ\w*,/киевск\w*\s+водохранилищ\w*
# ---------------------------------------------------------------- Chernihiv region
chernihiv; chernihiv; Chernihiv; 51.494; 31.289; C; чернігів,чернігов~,чернигов~
chernihiv; nizhyn; Nizhyn; 51.048; 31.886; T; ніжин~,нежин~
chernihiv; pryluky; Pryluky; 50.594; 32.387; T; прилук~,прилуц~
chernihiv; bakhmach; Bakhmach; 51.181; 32.828; T; бахмач~
chernihiv; koriukivka; Koriukivka; 51.770; 32.250; T; корюківк~,корюківц~
chernihiv; mena; Mena; 51.522; 32.214; T; мена,мену,меною
chernihiv; novhorod_siverskyi; Novhorod-Siverskyi; 51.983; 33.262; T; /новгород\w*-?\s?сіверськ\w*,/новгород\w*-?\s?северск\w*
chernihiv; semenivka_ch; Semenivka (Chernihiv reg.); 52.178; 32.583; T; семенівк~,семенівц~
chernihiv; horodnia; Horodnia; 51.894; 31.598; T; городн~
chernihiv; snovsk; Snovsk; 51.820; 31.950; T; сновськ~
chernihiv; ichnia; Ichnia; 50.862; 32.394; T; ічн~
chernihiv; borzna; Borzna; 51.253; 32.430; T; борзн~
chernihiv; kozelets; Kozelets; 50.913; 31.115; T; козелец~,козельц~
chernihiv; bobrovytsia; Bobrovytsia; 50.745; 31.380; T; бобровиц~
chernihiv; sosnytsia; Sosnytsia; 51.523; 32.495; T; сосниц~
chernihiv; oster; Oster; 50.946; 30.880; T; остер,остра,острі,остром
chernihiv; ripky; Ripky; 51.820; 31.080; T; ріпк~
chernihiv; liubech; Liubech; 51.700; 30.660; T; любеч~
chernihiv; varva; Varva; 50.500; 32.710; T; варв~
# ---------------------------------------------------------------- Sumy region
sumy; sumy; Sumy; 50.907; 34.798; C; суми,сум,сумах,сумам,сумами,сумы
sumy; konotop; Konotop; 51.240; 33.203; T; конотоп~
sumy; shostka; Shostka; 51.864; 33.473; T; шостк~,шостц~
sumy; okhtyrka; Okhtyrka; 50.310; 34.899; T; охтирк~,охтирц~,ахтырк~,ахтырц~
sumy; romny; Romny; 50.751; 33.474; T; ромн~,ромен
sumy; hlukhiv; Hlukhiv; 51.679; 33.913; T; глухів,глухов~
sumy; lebedyn; Lebedyn; 50.587; 34.484; T; лебедин~
sumy; trostianets; Trostianets; 50.477; 34.966; T; тростянец~,тростянц~
sumy; krolevets; Krolevets; 51.548; 33.385; T; кролевец~,кролевц~
sumy; bilopillia; Bilopillia; 51.150; 34.313; T; білопілл~,белопол~
sumy; putyvl; Putyvl; 51.337; 33.870; T; путивл~,путивль
sumy; seredyna_buda; Seredyna-Buda; 52.187; 34.035; T; /середин\w*-?\s?буд\w*
sumy; velyka_pysarivka; Velyka Pysarivka; 50.425; 35.481; T; /велик\w*\s+писарівк\w*
sumy; krasnopillia; Krasnopillia; 50.776; 35.270; T; краснопілл~
sumy; buryn; Buryn; 51.200; 33.840; T; бурин~,буринь
sumy; vorozhba; Vorozhba; 51.177; 34.226; T; ворожб~
sumy; nedryhailiv; Nedryhailiv; 50.835; 33.877; T; недригайлів,недригайлов~
sumy; esman; Esman; 51.889; 33.990; T; есман~,есмань
sumy; yampil_sumy; Yampil (Sumy reg.); 51.946; 33.788; T; ямпіл~,ямпол~
sumy; lypova_dolyna; Lypova Dolyna; 50.574; 33.799; T; /липов\w*\s+долин\w*
sumy; myropillia; Myropillia; 51.024; 35.257; T; миропілл~
sumy; svesa; Svesa; 51.947; 34.030; T; свес~
# ---------------------------------------------------------------- Kharkiv region
kharkiv; kharkiv; Kharkiv; 49.994; 36.230; C; харків,харков~,харьков~
kharkiv; kharkiv_saltivka; Saltivka (Kharkiv); 50.030; 36.300; D; салтівк~,салтівц~,салтовк~
kharkiv; kharkiv_kholodna_hora; Kholodna Hora (Kharkiv); 49.990; 36.180; D; /холодн\w*\s+гор\w*
kharkiv; kharkiv_nemyshlia; Nemyshlia (Kharkiv); 49.980; 36.320; D; немишл~
kharkiv; kupiansk; Kupiansk; 49.711; 37.616; T; куп'янськ~,купянск~
kharkiv; izium; Izium; 49.212; 37.256; T; ізюм~,изюм~
kharkiv; chuhuiv; Chuhuiv; 49.836; 36.689; T; чугуїв,чугуєв~,чугуев~
kharkiv; lozova; Lozova; 48.889; 36.317; T; лозов~
kharkiv; bohodukhiv; Bohodukhiv; 50.165; 35.527; T; богодухів,богодухов~
kharkiv; zolochiv_kh; Zolochiv (Kharkiv reg.); 50.280; 35.982; T; золочів,золочев~,золочов~
kharkiv; balakliia; Balakliia; 49.462; 36.858; T; балаклі~,балакле~
kharkiv; krasnohrad; Krasnohrad (Berestyn); 49.375; 35.441; T; красноград~,берестин~
kharkiv; merefa; Merefa; 49.820; 36.050; T; мереф~
kharkiv; pervomaiskyi; Pervomaiskyi; 49.389; 36.215; T; /первомайськ(?:ий|ого|ому|им)
kharkiv; zmiiv; Zmiiv; 49.680; 36.355; T; зміїв,змієв~,змиев~
kharkiv; vovchansk; Vovchansk; 50.290; 36.941; T; вовчанськ~,волчанск~
kharkiv; derhachi; Derhachi; 50.110; 36.120; T; дергач~
kharkiv; pisochyn; Pisochyn; 49.950; 36.090; T; пісочин~,песочин~
kharkiv; valky; Valky; 49.837; 35.614; T; валк~
kharkiv; barvinkove; Barvinkove; 48.906; 37.020; T; барвінков~
kharkiv; liubotyn; Liubotyn; 49.948; 35.928; T; люботин~
kharkiv; kozacha_lopan; Kozacha Lopan; 50.340; 36.210; T; /козач\w*\s+лопан\w*
kharkiv; velykyi_burluk; Velykyi Burluk; 50.060; 37.390; T; /велик\w*\s+бурлук\w*
kharkiv; borova; Borova; 49.376; 37.618; T; борова,борову,боровій
kharkiv; kolomak; Kolomak; 49.840; 35.290; T; коломак~
kharkiv; dvorichna; Dvorichna; 49.850; 37.680; T; дворічн~
# ---------------------------------------------------------------- Poltava region
poltava; poltava; Poltava; 49.589; 34.551; C; полтав~
poltava; kremenchuk; Kremenchuk; 49.066; 33.420; T; кременчу~,кременчуц~
poltava; horishni_plavni; Horishni Plavni; 49.010; 33.640; T; /горішн\w*\s+плавн\w*,/горишн\w*\s+плавн\w*
poltava; myrhorod; Myrhorod; 49.968; 33.608; T; миргород~
poltava; lubny; Lubny; 50.018; 32.997; T; лубн~,лубен
poltava; hadiach; Hadiach; 50.371; 34.000; T; гадяч~
poltava; hlobyne; Hlobyne; 49.393; 33.270; T; глобин~
poltava; karlivka; Karlivka; 49.459; 35.128; T; карлівк~,карлівц~,карловк~
poltava; kobeliaky; Kobeliaky; 49.147; 34.200; T; кобеляк~
poltava; reshetylivka; Reshetylivka; 49.563; 34.075; T; решетилівк~,решетилівц~
poltava; zinkiv; Zinkiv; 50.208; 34.367; T; зіньків,зінькова,зінькові
poltava; pyriatyn; Pyriatyn; 50.239; 32.511; T; пирятин~
poltava; khorol; Khorol; 49.785; 33.274; T; хорол~
poltava; lokhvytsia; Lokhvytsia; 50.360; 33.262; T; лохвиц~
poltava; chornukhy; Chornukhy; 50.283; 32.944; T; чорнух~
poltava; semenivka_pl; Semenivka (Poltava reg.); 49.596; 33.181; T; семенівк~,семенівц~
poltava; mashivka; Mashivka; 49.442; 34.866; T; машівк~,машівц~
poltava; novi_sanzhary; Novi Sanzhary; 49.333; 34.316; T; /нов\w*\s+санжар\w*
poltava; velyka_bahachka; Velyka Bahachka; 49.786; 33.744; T; /велик\w*\s+багачк\w*
poltava; dykanka; Dykanka; 49.822; 34.533; T; диканьк~,диканц~
poltava; kotelva; Kotelva; 50.068; 34.761; T; котельв~
poltava; chutove; Chutove; 49.715; 35.105; T; чутов~
poltava; orzhytsia; Orzhytsia; 49.795; 32.693; T; оржиц~
poltava; hrebinka; Hrebinka; 50.110; 32.441; T; гребінк~,гребінц~
poltava; shyshaky; Shyshaky; 49.892; 34.008; T; шишак~
poltava; velyki_sorochyntsi; Velyki Sorochyntsi; 49.970; 33.940; T; /велик\w*\s+сорочинц\w*
poltava; hradyzk; Hradyzk; 49.233; 33.133; T; градизьк~,градижськ~
poltava; opishnia; Opishnia; 49.958; 34.616; T; опішн~
poltava; kremenchuk_reservoir; Kremenchuk Reservoir; 49.30; 32.85; W; /кременчуцьк\w*\s+водосховищ\w*,/кременчугск\w*\s+водохранилищ\w*
# ---------------------------------------------------------------- Dnipropetrovsk region
dnipro; dnipro; Dnipro; 48.464; 35.046; C; дніпр~,днепр~
dnipro; kryvyi_rih; Kryvyi Rih; 47.910; 33.392; C; /крив(?:ий|ого|ому|им)\s+(?:ріг|рогу|розі|рогом),/крив(?:ой|ого|ом)\s+(?:рог|рога|роге),кривбас~
dnipro; kamianske; Kamianske; 48.512; 34.613; T; кам'янськ~
dnipro; nikopol; Nikopol; 47.567; 34.395; T; нікопол~,никопол~,нікополь
dnipro; pavlohrad; Pavlohrad; 48.534; 35.871; T; павлоград~
dnipro; marhanets; Marhanets; 47.648; 34.627; T; марганец~,марганц~
dnipro; synelnykove; Synelnykove; 48.318; 35.517; T; синельников~
dnipro; samar; Samar (Novomoskovsk); 48.633; 35.224; T; новомосковськ~,новомосковск~,самар,самарі
dnipro; pidhorodne; Pidhorodne; 48.574; 35.103; T; підгородн~
dnipro; pokrov; Pokrov; 47.653; 34.115; T; покров,покрові,покрова
dnipro; zhovti_vody; Zhovti Vody; 48.350; 33.500; T; /жовт\w*\s+вод\w*,/желт\w*\s+вод\w*
dnipro; vilnohirsk; Vilnohirsk; 48.486; 34.020; T; вільногірськ~
dnipro; piatykhatky; Piatykhatky; 48.413; 33.693; T; п'ятихатк~,п'ятихатц~,пятихатк~
dnipro; tsarychanka; Tsarychanka; 48.938; 34.476; T; царичанк~,царичанц~
dnipro; mezhova; Mezhova; 48.256; 36.735; T; межов~
dnipro; petropavlivka; Petropavlivka; 48.454; 36.448; T; петропавлівк~,петропавлівц~
dnipro; pokrovske; Pokrovske; 47.983; 36.230; T; /покровськ(?:е|ого|ому|им)
dnipro; apostolove; Apostolove; 47.661; 33.716; T; апостолов~
dnipro; verkhniodniprovsk; Verkhniodniprovsk; 48.656; 34.330; T; верхньодніпровськ~
dnipro; mahdalynivka; Mahdalynivka; 48.919; 34.886; T; магдалинівк~,магдалинівц~
dnipro; tomakivka; Tomakivka; 47.814; 34.745; T; томаківк~,томаківц~
dnipro; vasylkivka; Vasylkivka; 48.211; 36.026; T; васильківк~,васильківц~
dnipro; ternivka; Ternivka; 48.530; 36.070; T; тернівк~,тернівц~
dnipro; krynychky; Krynychky; 48.380; 34.460; T; криничк~,криничок
dnipro; sofiivka; Sofiivka; 48.070; 33.880; T; софіївк~,софіївц~
dnipro; zelenodolsk; Zelenodolsk; 47.570; 33.650; T; зеленодольськ~
# ---------------------------------------------------------------- Donetsk region
donetsk; kramatorsk; Kramatorsk; 48.723; 37.556; C; краматорськ~,краматорск~
donetsk; sloviansk; Sloviansk; 48.853; 37.605; T; слов'янськ~,славянск~
donetsk; druzhkivka; Druzhkivka; 48.630; 37.552; T; дружківк~,дружківц~,дружковк~
donetsk; kostiantynivka; Kostiantynivka; 48.528; 37.707; T; костянтинівк~,костянтинівц~,константиновк~
donetsk; pokrovsk; Pokrovsk; 48.283; 37.181; T; покровськ,покровська,покровську,покровськом,покровск,покровска
donetsk; dobropillia; Dobropillia; 48.469; 37.085; T; добропілл~,доброполь~
donetsk; myrnohrad; Myrnohrad; 48.302; 37.264; T; мирноград~
donetsk; bakhmut; Bakhmut; 48.595; 37.999; T; бахмут~
donetsk; mariupol; Mariupol; 47.097; 37.543; T; маріупол~,мариупол~,маріуполь
donetsk; donetsk; Donetsk; 48.016; 37.803; C; донецьк,донецька,донецьку,донецьком,донецк,донецка,донецке
donetsk; selydove; Selydove; 48.147; 37.300; T; селидов~
donetsk; kurakhove; Kurakhove; 47.983; 37.282; T; курахов~
donetsk; bilozerske; Bilozerske; 48.513; 37.064; T; білозерськ~
donetsk; sviatohirsk; Sviatohirsk; 49.033; 37.567; T; святогірськ~
donetsk; siversk; Siversk; 48.870; 38.100; T; сіверськ,сіверська,сіверську
donetsk; toretsk; Toretsk; 48.400; 37.850; T; торецьк~
donetsk; chasiv_yar; Chasiv Yar; 48.590; 37.840; T; /часов\w*\s+яр\w*,/часів\s+яр\w*
# ---------------------------------------------------------------- Zaporizhzhia region
zaporizhzhia; zaporizhzhia; Zaporizhzhia; 47.838; 35.139; C; запоріжж~,запорож~
zaporizhzhia; orikhiv; Orikhiv; 47.567; 35.784; T; оріхів,оріхов~,орехов~
zaporizhzhia; huliaipole; Huliaipole; 47.664; 36.256; T; гуляй-пол~
zaporizhzhia; vilniansk; Vilniansk; 47.946; 35.432; T; вільнянськ~,вольнянск~
zaporizhzhia; stepnohirsk; Stepnohirsk; 47.578; 35.338; T; степногірськ~
zaporizhzhia; melitopol; Melitopol; 46.849; 35.367; T; мелітопол~,мелитопол~,мелітополь
zaporizhzhia; berdiansk; Berdiansk; 46.756; 36.785; T; бердянськ~,бердянск~
zaporizhzhia; enerhodar; Enerhodar; 47.499; 34.656; T; енергодар~,энергодар~,заес
zaporizhzhia; tokmak; Tokmak; 47.256; 35.712; T; токмак~
zaporizhzhia; vasylivka; Vasylivka; 47.441; 35.276; T; василівк~,василівц~,васильевк~
zaporizhzhia; kamianka_dniprovska; Kamianka-Dniprovska; 47.476; 34.414; T; /кам'?янк\w*-?\s?дніпровськ\w*
# ---------------------------------------------------------------- Kherson region
kherson; kherson; Kherson; 46.636; 32.617; C; херсон~
kherson; beryslav; Beryslav; 46.840; 33.426; T; берислав~
kherson; nova_kakhovka; Nova Kakhovka; 46.755; 33.348; T; /нов\w*\s+каховк\w*
kherson; kakhovka; Kakhovka; 46.810; 33.480; T; каховк~,каховц~
kherson; hola_prystan; Hola Prystan; 46.523; 32.523; T; /гол\w*\s+пристан\w*
kherson; oleshky; Oleshky; 46.627; 32.716; T; олешк~,олешок
kherson; skadovsk; Skadovsk; 46.116; 32.913; T; скадовськ~,скадовск~
kherson; bilozerka; Bilozerka; 46.638; 32.442; T; білозерк~,білозерц~
kherson; velyka_oleksandrivka; Velyka Oleksandrivka; 47.312; 33.300; T; /велик\w*\s+олександрівк\w*
kherson; vysokopillia; Vysokopillia; 47.474; 33.534; T; високопілл~
kherson; chornobaivka; Chornobaivka; 46.693; 32.553; T; чорнобаївк~,чорнобаївц~
kherson; antonivka; Antonivka; 46.680; 32.715; T; антонівк~,антонівц~
kherson; left_bank; Left bank (Kherson); 46.550; 33.000; W; лівобережж~
# ---------------------------------------------------------------- Mykolaiv region
mykolaiv; mykolaiv; Mykolaiv; 46.975; 31.995; C; миколаїв,миколаєв~,николаев~
mykolaiv; voznesensk; Voznesensk; 47.567; 31.333; T; вознесенськ~,вознесенск~
mykolaiv; pervomaisk; Pervomaisk; 48.050; 30.850; T; первомайськ,первомайська,первомайську,первомайськом,первомайск,первомайска
mykolaiv; ochakiv; Ochakiv; 46.613; 31.547; T; очаків,очакова,очакові,очаков~
mykolaiv; yuzhnoukrainsk; Yuzhnoukrainsk; 47.833; 31.183; T; южноукраїнськ~,южноукраинск~,паес
mykolaiv; bashtanka; Bashtanka; 47.408; 32.439; T; баштанк~,баштанц~
mykolaiv; novyi_buh; Novyi Buh; 47.687; 32.513; T; /нов\w*\s+буг\w*
mykolaiv; snihurivka; Snihurivka; 47.073; 32.807; T; снігурівк~,снігурівц~
mykolaiv; nova_odesa; Nova Odesa; 47.311; 31.788; T; /нов\w*\s+одес\w*
mykolaiv; kazanka; Kazanka; 47.837; 32.840; T; казанк~,казанц~
mykolaiv; bratske; Bratske; 47.862; 31.581; T; /братськ(?:е|ого|ому)
mykolaiv; koblevo; Koblevo; 46.670; 31.210; T; коблев~
mykolaiv; bereznehuvate; Bereznehuvate; 47.313; 32.851; T; березнегуват~
mykolaiv; arbuzynka; Arbuzynka; 47.900; 31.320; T; арбузинк~,арбузинц~
mykolaiv; domanivka; Domanivka; 47.633; 30.990; T; доманівк~,доманівц~
mykolaiv; vradiivka; Vradiivka; 47.860; 30.590; T; врадіївк~,врадіївц~
mykolaiv; kinburn; Kinburn Spit; 46.550; 31.550; W; кінбурн~
# ---------------------------------------------------------------- Odesa region
odesa; odesa; Odesa; 46.482; 30.723; C; одес~
odesa; izmail; Izmail; 45.351; 28.837; T; ізмаїл~,измаил~
odesa; reni; Reni; 45.457; 28.290; T; рені,рени
odesa; bilhorod_dnistrovskyi; Bilhorod-Dnistrovskyi; 46.191; 30.334; T; /білгород\w*-?\s?дністров\w*,/белгород\w*-?\s?днестров\w*,аккерман~,білгород~
odesa; chornomorsk; Chornomorsk; 46.300; 30.655; T; чорноморськ~,черноморск~,іллічівськ~
odesa; pivdenne; Pivdenne (Yuzhne); 46.623; 31.101; T; южне,южного,южному
odesa; zatoka; Zatoka; 46.071; 30.465; T; затока,затоку,затоки,затоці,затокою
odesa; podilsk; Podilsk; 47.743; 29.533; T; подільськ,подільська,подільську,подольск~
odesa; balta; Balta; 47.938; 29.619; T; балт~
odesa; rozdilna; Rozdilna; 46.849; 30.078; T; роздільн~,раздельн~
odesa; berezivka; Berezivka; 47.204; 30.913; T; березівк~,березівц~,березовк~
odesa; artsyz; Artsyz; 45.993; 29.418; T; арциз~
odesa; bolhrad; Bolhrad; 45.682; 28.613; T; болград~
odesa; kiliia; Kiliia; 45.455; 29.264; T; кілі~,килия,килии
odesa; vylkove; Vylkove; 45.405; 29.587; T; вилков~
odesa; tatarbunary; Tatarbunary; 45.838; 29.616; T; татарбунар~
odesa; sarata; Sarata; 46.018; 29.666; T; сарат~
odesa; ovidiopol; Ovidiopol; 46.255; 30.437; T; овідіопол~,овидиопол~,овідіополь
odesa; kodyma; Kodyma; 48.098; 29.124; T; кодим~
odesa; ananiv; Ananiv; 47.722; 29.968; T; ананьїв,ананьєв~,ананьев~
odesa; liubashivka; Liubashivka; 47.837; 30.258; T; любашівк~,любашівц~
odesa; velyka_mykhailivka; Velyka Mykhailivka; 47.074; 29.854; T; /велик\w*\s+михайлівк\w*
odesa; shyriaieve; Shyriaieve; 47.400; 30.190; T; ширяєв~,ширяев~
odesa; teplodar; Teplodar; 46.505; 30.330; T; теплодар~
odesa; biliaivka; Biliaivka; 46.480; 30.200; T; біляївк~,біляївц~
odesa; karolino_buhaz; Karolino-Buhaz; 46.150; 30.530; T; кароліно-бугаз~
odesa; danube; Danube; 45.350; 29.000; W; дунай,дунаю,дунаї,дунаєм
odesa; zmiinyi; Zmiinyi Island; 45.255; 30.204; W; /зміїн\w*\s+остр\w*,/зміїн(?:ий|ого|ому)
sea; black_sea; Black Sea; 45.60; 31.60; W; /чорн\w*\s+мор\w*,/черн\w*\s+мор\w*
sea; azov_sea; Sea of Azov; 46.20; 36.60; W; /азовськ\w*\s+мор\w*,/азовск\w*\s+мор\w*
# ---------------------------------------------------------------- Cherkasy region
cherkasy; cherkasy; Cherkasy; 49.444; 32.060; C; черкас~,черкасс~
cherkasy; uman; Uman; 48.749; 30.221; T; уман~,умань
cherkasy; smila; Smila; 49.224; 31.879; T; сміла,смілу,смілі,смілою,смела,смелу
cherkasy; zolotonosha; Zolotonosha; 49.668; 32.039; T; золотонош~
cherkasy; kaniv; Kaniv; 49.751; 31.464; T; канів,канев~
cherkasy; zvenyhorodka; Zvenyhorodka; 49.078; 30.963; T; звенигородк~,звенигородц~
cherkasy; korsun; Korsun-Shevchenkivskyi; 49.419; 31.256; T; корсун~,корсунь~
cherkasy; shpola; Shpola; 49.008; 31.389; T; шпол~
cherkasy; talne; Talne; 48.884; 30.704; T; тальн~
cherkasy; khrystynivka; Khrystynivka; 48.833; 29.968; T; христинівк~,христинівц~
cherkasy; chyhyryn; Chyhyryn; 49.081; 32.656; T; чигирин~
cherkasy; kamianka_ch; Kamianka (Cherkasy reg.); 49.031; 32.103; T; кам'янк~,кам'янц~
cherkasy; horodyshche; Horodyshche; 49.290; 31.450; T; городищ~
cherkasy; monastyryshche; Monastyryshche; 48.989; 29.803; T; монастирищ~
cherkasy; zhashkiv; Zhashkiv; 49.243; 30.112; T; жашків,жашков~
cherkasy; chornobai; Chornobai; 49.668; 32.326; T; чорнобай,чорнобаю,чорнобаї
cherkasy; drabiv; Drabiv; 49.966; 32.143; T; драбів,драбова,драбові
cherkasy; kaniv_reservoir; Kaniv Reservoir; 49.95; 31.25; W; /канівськ\w*\s+водосховищ\w*
# ---------------------------------------------------------------- Kirovohrad region
kirovohrad; kropyvnytskyi; Kropyvnytskyi; 48.508; 32.262; C; кропивницьк~,кропивницк~,кіровоград~,кировоград~
kirovohrad; oleksandriia; Oleksandriia; 48.672; 33.117; T; олександрія,олександрії,олександрію,олександрією,александрия,александрии
kirovohrad; svitlovodsk; Svitlovodsk; 49.049; 33.241; T; світловодськ~,светловодск~
kirovohrad; znamianka; Znamianka; 48.716; 32.672; T; знам'янк~,знам'янц~,знаменк~
kirovohrad; holovanivsk; Holovanivsk; 48.381; 30.454; T; голованівськ~
kirovohrad; novoukrainka; Novoukrainka; 48.318; 31.527; T; новоукраїнк~,новоукраїнц~,новоукраинк~
kirovohrad; dolynska; Dolynska; 48.111; 32.765; T; /долинськ(?:а|ої|ій|у)
kirovohrad; haivoron; Haivoron; 48.336; 29.865; T; гайворон~
kirovohrad; mala_vyska; Mala Vyska; 48.650; 31.640; T; /мал\w*\s+виск\w*
kirovohrad; bobrynets; Bobrynets; 48.058; 32.157; T; бобринец~,бобринц~
kirovohrad; novomyrhorod; Novomyrhorod; 48.781; 31.646; T; новомиргород~
kirovohrad; blahovishchenske; Blahovishchenske; 48.312; 30.233; T; благовіщенськ~
kirovohrad; petrove; Petrove; 48.346; 33.264; T; петрове,петрового,петровому
kirovohrad; onufriivka; Onufriivka; 48.903; 33.448; T; онуфріївк~,онуфріївц~
kirovohrad; novhorodka; Novhorodka; 48.360; 32.650; T; новгородк~,новгородц~
kirovohrad; kompaniivka; Kompaniivka; 48.010; 32.200; T; компаніївк~,компаніївц~
kirovohrad; dobrovelychkivka; Dobrovelychkivka; 48.380; 31.180; T; добровеличківк~,добровеличківц~
# ---------------------------------------------------------------- Vinnytsia region
vinnytsia; vinnytsia; Vinnytsia; 49.233; 28.468; C; вінниц~,винниц~
vinnytsia; zhmerynka; Zhmerynka; 49.038; 28.111; T; жмеринк~,жмеринц~
vinnytsia; koziatyn; Koziatyn; 49.716; 28.833; T; козятин~,казатин~
vinnytsia; kalynivka; Kalynivka; 49.454; 28.524; T; калинівк~,калинівц~,калиновк~
vinnytsia; ladyzhyn; Ladyzhyn; 48.684; 29.236; T; ладижин~
vinnytsia; haisyn; Haisyn; 48.810; 29.390; T; гайсин~
vinnytsia; mohyliv_podilskyi; Mohyliv-Podilskyi; 48.446; 27.798; T; /могил[іе]в\w*-?\s?поділ\w*
vinnytsia; khmilnyk; Khmilnyk; 49.560; 27.957; T; хмільник~
vinnytsia; tulchyn; Tulchyn; 48.676; 28.848; T; тульчин~
vinnytsia; bershad; Bershad; 48.369; 29.517; T; бершад~
vinnytsia; nemyriv; Nemyriv; 48.971; 28.837; T; немирів,немиров~
vinnytsia; illintsi; Illintsi; 49.105; 29.218; T; іллінц~,іллінець
vinnytsia; pohrebyshche; Pohrebyshche; 49.487; 29.264; T; погребищ~
vinnytsia; lypovets; Lypovets; 49.214; 29.058; T; липовец~,липовц~
vinnytsia; yampil_vn; Yampil (Vinnytsia reg.); 48.244; 28.281; T; ямпіл~,ямпол~
vinnytsia; sharhorod; Sharhorod; 48.751; 28.081; T; шаргород~
vinnytsia; tyvriv; Tyvriv; 49.012; 28.509; T; тиврів,тиврова,тиврові
vinnytsia; kryzhopil; Kryzhopil; 48.384; 28.866; T; крижопіл~,крижопол~,крижопіль
vinnytsia; orativ; Orativ; 49.190; 29.520; T; оратів,оратова,оратові
vinnytsia; teplyk; Teplyk; 48.670; 29.740; T; теплик~
vinnytsia; chechelnyk; Chechelnyk; 48.210; 29.360; T; чечельник~
vinnytsia; hnivan; Hnivan; 49.100; 28.350; T; гнівань,гнівані,гнівань~
vinnytsia; vapniarka; Vapniarka; 48.530; 28.750; T; вапнярк~,вапнярц~
vinnytsia; tomashpil; Tomashpil; 48.550; 28.520; T; томашпіл~,томашпол~
# ---------------------------------------------------------------- Zhytomyr region
zhytomyr; zhytomyr; Zhytomyr; 50.254; 28.658; C; житомир~
zhytomyr; berdychiv; Berdychiv; 49.899; 28.602; T; бердичів,бердичев~
zhytomyr; korosten; Korosten; 50.956; 28.639; T; коростен~,коростень
zhytomyr; zviahel; Zviahel; 50.590; 27.617; T; звягел~,звягель,/новоград\w*-?\s?волинськ\w*
zhytomyr; ovruch; Ovruch; 51.324; 28.809; T; овруч~
zhytomyr; malyn; Malyn; 50.773; 29.233; T; малин,малина,малині,малину,малином
zhytomyr; korostyshiv; Korostyshiv; 50.320; 29.058; T; коростишів,коростишев~
zhytomyr; radomyshl; Radomyshl; 50.497; 29.234; T; радомишл~,радомишль
zhytomyr; chudniv; Chudniv; 50.051; 28.112; T; чуднів,чуднов~
zhytomyr; olevsk; Olevsk; 51.215; 27.656; T; олевськ~
zhytomyr; baranivka; Baranivka; 50.297; 27.666; T; баранівк~,баранівц~
zhytomyr; andrushivka; Andrushivka; 50.020; 29.017; T; андрушівк~,андрушівц~
zhytomyr; popilnia; Popilnia; 49.946; 29.452; T; попільн~
zhytomyr; ruzhyn; Ruzhyn; 49.723; 29.217; T; ружин~
zhytomyr; narodychi; Narodychi; 51.202; 29.083; T; народич~
zhytomyr; luhyny; Luhyny; 51.075; 28.398; T; лугин~
zhytomyr; yemilchyne; Yemilchyne; 50.874; 27.807; T; ємільчин~
zhytomyr; liubar; Liubar; 49.922; 27.738; T; любар~
zhytomyr; cherniakhiv; Cherniakhiv; 50.456; 28.672; T; черняхів,черняхов~
zhytomyr; brusyliv; Brusyliv; 50.284; 29.521; T; брусилів,брусилова,брусилові
zhytomyr; khoroshiv; Khoroshiv; 50.598; 28.460; T; хорошів,хорошева,хорошеві
# ---------------------------------------------------------------- Khmelnytskyi region
khmelnytskyi; khmelnytskyi; Khmelnytskyi; 49.422; 26.987; C; хмельницьк~,хмельницк~
khmelnytskyi; kamianets_podilskyi; Kamianets-Podilskyi; 48.678; 26.585; T; /кам'?ян[еє]?ц\w*\s*-?\s*поділ\w*,/каменец\w*-?\s?подол\w*
khmelnytskyi; shepetivka; Shepetivka; 50.183; 27.063; T; шепетівк~,шепетівц~,шепетовк~
khmelnytskyi; starokostiantyniv; Starokostiantyniv; 49.756; 27.208; T; старокостянтинів,старокостянтинов~,староконстантинов~
khmelnytskyi; netishyn; Netishyn; 50.340; 26.640; T; нетішин~,хаес
khmelnytskyi; slavuta; Slavuta; 50.300; 26.869; T; славута,славуту,славуті,славутою
khmelnytskyi; polonne; Polonne; 50.118; 27.523; T; полонн~
khmelnytskyi; krasyliv; Krasyliv; 49.651; 26.977; T; красилів,красилова,красилові
khmelnytskyi; volochysk; Volochysk; 49.534; 26.205; T; волочиськ~
khmelnytskyi; iziaslav; Iziaslav; 50.118; 26.795; T; ізяслав~
khmelnytskyi; derazhnia; Derazhnia; 49.267; 27.433; T; деражн~
khmelnytskyi; letychiv; Letychiv; 49.381; 27.616; T; летичів,летичев~
khmelnytskyi; dunaivtsi; Dunaivtsi; 48.889; 26.855; T; дунаївц~,дунаївець
khmelnytskyi; yarmolyntsi; Yarmolyntsi; 49.190; 26.840; T; ярмолинц~
# ---------------------------------------------------------------- Rivne region
rivne; rivne; Rivne; 50.619; 26.251; C; рівне,рівного,рівному,рівним
rivne; dubno; Dubno; 50.417; 25.735; T; дубн~
rivne; sarny; Sarny; 51.338; 26.601; T; сарн~
rivne; varash; Varash; 51.349; 25.851; T; вараш~,кузнецовськ~,раес
rivne; kostopil; Kostopil; 50.879; 26.445; T; костопіл~,костопол~,костопіль
rivne; zdolbuniv; Zdolbuniv; 50.506; 26.244; T; здолбунів,здолбунов~
rivne; ostroh; Ostroh; 50.329; 26.513; T; острог~
rivne; dubrovytsia; Dubrovytsia; 51.574; 26.568; T; дубровиц~
rivne; rokytne; Rokytne; 51.282; 27.214; T; рокитн~
rivne; berezne; Berezne; 51.000; 26.746; T; /березн(?:е|ого|ому)
rivne; korets; Korets; 50.618; 27.162; T; корец~,корц~
rivne; radyvyliv; Radyvyliv; 50.130; 25.258; T; радивилів,радивилова,радивилові
rivne; volodymyrets; Volodymyrets; 51.418; 26.143; T; володимирец~,володимирц~
rivne; zarichne; Zarichne; 51.810; 26.130; T; /зарічн(?:е|ого|ому)
rivne; klevan; Klevan; 50.740; 25.980; T; клевань,клеван~
# ---------------------------------------------------------------- Volyn region
volyn; lutsk; Lutsk; 50.747; 25.325; C; луцьк~,луцк~
volyn; kovel; Kovel; 51.215; 24.708; T; ковел~,ковель
volyn; volodymyr; Volodymyr; 50.849; 24.320; T; /володимир\w*-?\s?волинськ\w*,/владимир\w*-?\s?волынск\w*
volyn; novovolynsk; Novovolynsk; 50.725; 24.165; T; нововолинськ~
volyn; kamin_kashyrskyi; Kamin-Kashyrskyi; 51.623; 24.960; T; /кам(?:і|е)нь\w*-?\s?каширськ\w*
volyn; liubeshiv; Liubeshiv; 51.761; 25.509; T; любешів,любешова,любешові
volyn; manevychi; Manevychi; 51.297; 25.536; T; маневич~
volyn; kivertsi; Kivertsi; 50.836; 25.457; T; ківерц~
volyn; horokhiv; Horokhiv; 50.502; 24.763; T; горохів,горохова,горохові
volyn; ratne; Ratne; 51.668; 24.523; T; /ратн(?:е|ого|ому)
volyn; shatsk; Shatsk; 51.490; 23.930; T; шацьк~
volyn; liuboml; Liuboml; 51.226; 24.041; T; любомл~,любомль
volyn; rozhyshche; Rozhyshche; 50.915; 25.270; T; рожищ~
volyn; starovyzhivka; Stara Vyzhivka; 51.440; 23.920; T; старовижівк~
# ---------------------------------------------------------------- Lviv region
lviv; lviv; Lviv; 49.842; 24.031; C; львів,львов~
lviv; stryi; Stryi; 49.256; 23.851; T; стрий,стрия,стрию,стриї,стриєм
lviv; drohobych; Drohobych; 49.349; 23.507; T; дрогобич~
lviv; sambir; Sambir; 49.518; 23.197; T; самбір,самбор~
lviv; sheptytskyi; Sheptytskyi (Chervonohrad); 50.391; 24.228; T; червоноград~,/шептицьк(?:ий|ого|ому|им)
lviv; truskavets; Truskavets; 49.278; 23.505; T; трускавец~,трускавц~
lviv; zolochiv_lv; Zolochiv (Lviv reg.); 49.807; 24.903; T; золочів,золочев~,золочов~
lviv; brody; Brody; 50.087; 25.150; T; броди,бродах
lviv; yavoriv; Yavoriv; 49.938; 23.383; T; яворів,яворов~
lviv; zhovkva; Zhovkva; 50.056; 23.971; T; жовкв~
lviv; mostyska; Mostyska; 49.795; 23.150; T; мостиськ~
lviv; novoiavorivsk; Novoiavorivsk; 49.931; 23.573; T; новояворівськ~
lviv; sokal; Sokal; 50.481; 24.282; T; сокал~,сокаль
lviv; busk; Busk; 49.967; 24.611; T; буськ~
lviv; radekhiv; Radekhiv; 50.281; 24.637; T; радехів,радехова,радехові
lviv; pustomyty; Pustomyty; 49.718; 23.906; T; пустомит~
lviv; skole; Skole; 49.039; 23.513; T; сколе,сколього
lviv; boryslav; Boryslav; 49.287; 23.427; T; борислав~
lviv; zhydachiv; Zhydachiv; 49.385; 24.143; T; жидачів,жидачев~
lviv; khodoriv; Khodoriv; 49.410; 24.310; T; ходорів,ходорова,ходорові
lviv; peremyshliany; Peremyshliany; 49.665; 24.557; T; перемишлян~
lviv; kamianka_buzka; Kamianka-Buzka; 50.100; 24.350; T; /кам'?янк\w*-?\s?бузьк\w*
# ---------------------------------------------------------------- Ivano-Frankivsk region
ivano_frankivsk; ivano_frankivsk; Ivano-Frankivsk; 48.922; 24.711; C; /івано-?\s?франківськ\w*,франківськ~,/ивано-?\s?франковск\w*,франковск~
ivano_frankivsk; kolomyia; Kolomyia; 48.531; 25.040; T; коломи~,коломы~
ivano_frankivsk; kalush; Kalush; 49.026; 24.373; T; калуш~
ivano_frankivsk; burshtyn; Burshtyn; 49.259; 24.627; T; бурштин~
ivano_frankivsk; nadvirna; Nadvirna; 48.634; 24.576; T; надвірн~
ivano_frankivsk; bolekhiv; Bolekhiv; 49.067; 23.849; T; болехів,болехова,болехові
ivano_frankivsk; kosiv; Kosiv; 48.317; 25.096; T; косів,косові
ivano_frankivsk; yaremche; Yaremche; 48.457; 24.556; T; яремч~
ivano_frankivsk; tysmenytsia; Tysmenytsia; 48.900; 24.849; T; тисмениц~
ivano_frankivsk; halych; Halych; 49.124; 24.729; T; галич,галича,галичі
ivano_frankivsk; rohatyn; Rohatyn; 49.410; 24.609; T; рогатин~
ivano_frankivsk; horodenka; Horodenka; 48.667; 25.500; T; городенк~,городенц~
ivano_frankivsk; sniatyn; Sniatyn; 48.447; 25.567; T; снятин~
ivano_frankivsk; tlumach; Tlumach; 48.866; 25.000; T; тлумач~
ivano_frankivsk; verkhovyna; Verkhovyna; 48.155; 24.817; T; верховин~
# ---------------------------------------------------------------- Ternopil region
ternopil; ternopil; Ternopil; 49.553; 25.594; C; тернопіль,тернопол~
ternopil; chortkiv; Chortkiv; 49.017; 25.798; T; чортків,чортков~
ternopil; kremenets; Kremenets; 50.105; 25.728; T; кременец~,кременц~
ternopil; berezhany; Berezhany; 49.448; 24.936; T; бережан~
ternopil; zbarazh; Zbarazh; 49.664; 25.778; T; збараж~
ternopil; terebovlia; Terebovlia; 49.302; 25.700; T; теребовл~
ternopil; zalishchyky; Zalishchyky; 48.643; 25.736; T; заліщик~
ternopil; buchach; Buchach; 49.061; 25.390; T; бучач~
ternopil; lanivtsi; Lanivtsi; 49.862; 26.091; T; ланівц~
ternopil; pidvolochysk; Pidvolochysk; 49.528; 26.143; T; підволочиськ~
ternopil; borshchiv; Borshchiv; 48.803; 26.042; T; борщів,борщева,борщеві
ternopil; husiatyn; Husiatyn; 49.072; 26.183; T; гусятин~
ternopil; shumsk; Shumsk; 50.117; 26.112; T; шумськ~
ternopil; pochaiv; Pochaiv; 50.008; 25.508; T; почаїв,почаєв~
ternopil; kozova; Kozova; 49.430; 25.152; T; козов~
# ---------------------------------------------------------------- Chernivtsi region
chernivtsi; chernivtsi; Chernivtsi; 48.292; 25.936; C; чернівц~,чернівець,черновц~,черновиц~
chernivtsi; khotyn; Khotyn; 48.507; 26.495; T; хотин~
chernivtsi; novodnistrovsk; Novodnistrovsk; 48.580; 27.442; T; новодністровськ~
chernivtsi; storozhynets; Storozhynets; 48.161; 25.719; T; сторожинец~,сторожинц~
chernivtsi; kitsman; Kitsman; 48.442; 25.762; T; кіцман~,кіцмань
chernivtsi; vyzhnytsia; Vyzhnytsia; 48.250; 25.188; T; вижниц~
chernivtsi; sokyriany; Sokyriany; 48.448; 27.418; T; сокирян~
chernivtsi; kelmentsi; Kelmentsi; 48.477; 26.833; T; кельменц~
chernivtsi; novoselytsia; Novoselytsia; 48.219; 26.270; T; новоселиц~
# ---------------------------------------------------------------- Zakarpattia region
zakarpattia; uzhhorod; Uzhhorod; 48.621; 22.288; C; ужгород~
zakarpattia; mukachevo; Mukachevo; 48.440; 22.718; T; мукачев~,мукачів
zakarpattia; berehove; Berehove; 48.205; 22.645; T; берегове,берегового,береговому
zakarpattia; khust; Khust; 48.170; 23.290; T; хуст~
zakarpattia; rakhiv; Rakhiv; 48.054; 24.200; T; рахів,рахов~
zakarpattia; svaliava; Svaliava; 48.546; 22.988; T; свалява,сваляви,сваляві,сваляву
zakarpattia; vynohradiv; Vynohradiv; 48.141; 23.033; T; виноградів,виноградова,виноградові
zakarpattia; tiachiv; Tiachiv; 48.012; 23.572; T; тячів,тячева,тячеві
zakarpattia; irshava; Irshava; 48.317; 23.034; T; іршав~
zakarpattia; chop; Chop; 48.432; 22.204; T; чоп,чопа,чопі
zakarpattia; perechyn; Perechyn; 48.736; 22.476; T; перечин~
zakarpattia; velykyi_bereznyi; Velykyi Bereznyi; 48.890; 22.459; T; /велик\w*\s+березн\w*
zakarpattia; mizhhiria; Mizhhiria; 48.528; 23.505; T; міжгір~
# ---------------------------------------------------------------- Luhansk region
luhansk; luhansk; Luhansk; 48.574; 39.307; C; луганськ,луганська,луганську,луганськом,луганск,луганска,луганске
luhansk; sievierodonetsk; Sievierodonetsk; 48.948; 38.491; T; сєвєродонецьк~,северодонецк~
luhansk; lysychansk; Lysychansk; 48.905; 38.443; T; лисичанськ~,лисичанск~
luhansk; starobilsk; Starobilsk; 49.278; 38.910; T; старобільськ~,старобельск~
luhansk; svatove; Svatove; 49.410; 38.150; T; сватов~
luhansk; kreminna; Kreminna; 49.050; 38.217; T; кремінн~,кременн~
# ---------------------------------------------------------------- Crimea
crimea; sevastopol; Sevastopol; 44.616; 33.525; C; севастопол~,севастополь
crimea; simferopol; Simferopol; 44.952; 34.102; C; сімферопол~,симферопол~,сімферополь
crimea; kerch; Kerch; 45.357; 36.468; T; керч~
crimea; dzhankoi; Dzhankoi; 45.709; 34.390; T; джанко~
crimea; feodosiia; Feodosiia; 45.031; 35.383; T; феодосі~,феодоси~
crimea; yevpatoriia; Yevpatoriia; 45.190; 33.367; T; євпаторі~,евпатори~
crimea; saky; Saky; 45.130; 33.600; T; саки,саках
crimea; chauda; Cape Chauda; 45.000; 35.840; F; чауд~
crimea; hvardiiske; Hvardiiske; 45.115; 34.017; F; гвардійськ~,гвардейск~
crimea; belbek; Belbek; 44.690; 33.580; F; бельбек~
crimea; tarkhankut; Cape Tarkhankut; 45.350; 32.500; W; тарханкут~
crimea; armiansk; Armiansk; 46.106; 33.692; T; армянськ~
# ---------------------------------------------------------------- Russia: cities and border districts (regions come from data/regions.json)
ru_bel; belgorod; Belgorod; 50.597; 36.588; F; бєлгород~,белгород~,білгород~
ru_bel; shebekino; Shebekino; 50.410; 36.890; F; шебекін~,шебекин~,/шебекинск\w*\s+(?:округ|район)\w*
ru_bel; graivoron; Graivoron; 50.480; 35.680; F; грайворон~
ru_bel; valuyki; Valuyki; 50.210; 38.100; F; валуйк~,валуйок,/валуйск\w*\s+(?:округ|район)\w*
ru_bel; stroitel; Yakovlevsky district; 50.790; 36.480; F; /яковлевск\w*\s+(?:округ|район)\w*,строител~
ru_bel; krasnaya_yaruga; Krasnaya Yaruga; 50.700; 35.710; F; /краснояружск\w*\s+(?:округ|район)\w*,/красн\w*\s+яруг\w*
ru_bel; ivnya; Ivnya; 51.080; 36.130; F; /ивнянск\w*\s+(?:округ|район)\w*,ивн~
ru_bel; borisovka; Borisovka; 50.600; 36.010; F; /борисовск\w*\s+(?:округ|район)\w*,борисовк~
ru_bel; rakitnoye; Rakitnoye; 50.840; 35.860; F; /ракитянск\w*\s+(?:округ|район)\w*
ru_bel; belgorod_district; Belgorodsky district; 50.560; 36.480; F; /белгородск\w*\s+(?:округ|район)\w*
ru_bel; volokonovka; Volokonovka; 50.480; 37.860; F; волоконовк~,/волоконовск\w*\s+(?:округ|район)\w*
ru_bel; gubkin; Gubkin; 51.280; 37.540; F; губкин,губкине,губкина
ru_bel; stary_oskol; Stary Oskol; 51.300; 37.840; F; /стар\w*\s+оскол\w*
ru_bel; novy_oskol; Novy Oskol; 50.760; 37.870; F; /нов\w*\s+оскол\w*
ru_bel; alekseyevka; Alekseyevka; 50.630; 38.690; F; /алексеевск\w*\s+(?:округ|район)\w*
ru_bel; korocha; Korocha; 50.810; 37.190; F; короч~
ru_bel; prokhorovka; Prokhorovka; 51.040; 36.730; F; прохоровк~
ru_krs; kursk; Kursk; 51.730; 36.193; F; курськ~,курск~
ru_krs; sudzha; Sudzha; 51.190; 35.270; F; судж~
ru_krs; rylsk; Rylsk; 51.570; 34.680; F; рыльск~,рильськ~
ru_krs; glushkovo; Glushkovo; 51.340; 34.650; F; глушков~
ru_krs; korenevo; Korenevo; 51.400; 34.910; F; коренев~
ru_krs; lgov; Lgov; 51.660; 35.270; F; льгов~
ru_krs; kurchatov; Kurchatov; 51.660; 35.650; F; курчатов~
ru_krs; zheleznogorsk; Zheleznogorsk; 52.340; 35.350; F; железногорск~
ru_krs; oboyan; Oboyan; 51.210; 36.270; F; обоян~
ru_krs; khomutovka; Khomutovka; 51.920; 34.550; F; хомутовк~
ru_bry; bryansk; Bryansk; 53.243; 34.364; F; брянськ~,брянск~
ru_bry; klintsy; Klintsy; 52.750; 32.240; F; клинц~,клинцы
ru_bry; klimovo; Klimovo; 52.380; 32.190; F; климов~
ru_bry; starodub; Starodub; 52.590; 32.760; F; стародуб~
ru_bry; pogar; Pogar; 52.550; 33.260; F; погар~
ru_bry; trubchevsk; Trubchevsk; 52.580; 33.770; F; трубчевск~
ru_bry; suzemka; Suzemka; 52.320; 34.080; F; суземк~
ru_bry; sevsk; Sevsk; 52.150; 34.490; F; севск~
ru_bry; novozybkov; Novozybkov; 52.540; 31.930; F; новозыбков~
ru_bry; unecha; Unecha; 52.850; 32.680; F; унеч~
ru_bry; pochep; Pochep; 52.930; 33.450; F; почеп~
ru_bry; zlynka; Zlynka; 52.430; 31.730; F; злынк~
ru_vor; voronezh; Voronezh; 51.670; 39.200; F; воронеж~
ru_vor; rossosh; Rossosh; 50.200; 39.570; F; россош~
ru_vor; boguchar; Boguchar; 49.940; 40.550; F; богучар~
ru_vor; liski; Liski; 50.980; 39.500; F; лиски,лисках
ru_ros; rostov; Rostov-on-Don; 47.235; 39.700; F; ростов~
ru_ros; taganrog; Taganrog; 47.210; 38.940; F; таганрог~
ru_ros; millerovo; Millerovo; 48.920; 40.400; F; міллеров~,миллеров~
ru_ros; morozovsk; Morozovsk; 48.350; 41.830; F; морозовськ~,морозовск~
ru_ros; novoshakhtinsk; Novoshakhtinsk; 47.760; 39.930; F; новошахтинск~
ru_ros; kamensk; Kamensk-Shakhtinsky; 48.320; 40.260; F; /каменск\w*-?\s?шахтинск\w*
ru_ros; azov; Azov; 47.110; 39.420; F; азов,азова,азове
ru_ros; shakhty; Shakhty; 47.710; 40.210; F; шахты,шахтах
ru_ros; novocherkassk; Novocherkassk; 47.420; 40.090; F; новочеркасск~
ru_ros; volgodonsk; Volgodonsk; 47.510; 42.150; F; волгодонск~
ru_kda; krasnodar; Krasnodar; 45.040; 38.980; F; краснодар,краснодара,краснодаре
ru_kda; novorossiysk; Novorossiysk; 44.720; 37.770; F; новоросійськ~,новороссийск~
ru_kda; tuapse; Tuapse; 44.100; 39.080; F; туапсе
ru_kda; sochi; Sochi; 43.600; 39.730; F; сочи
ru_kda; anapa; Anapa; 44.890; 37.320; F; анап~
ru_kda; temryuk; Temryuk; 45.270; 37.380; F; темрюк~
ru_kda; yeysk; Yeysk; 46.710; 38.270; F; єйськ~,ейск~
ru_kda; primorsko_akhtarsk; Primorsko-Akhtarsk; 46.050; 38.170; F; /приморсько-?\s?ахтарськ\w*,/приморско-?\s?ахтарск\w*,ахтарск~
ru_kda; armavir; Armavir; 45.000; 41.120; F; армавир~
ru_kda; tikhoretsk; Tikhoretsk; 45.850; 40.120; F; тихорецк~
ru_kda; slavyansk_kuban; Slavyansk-na-Kubani; 45.260; 38.120; F; /славянск\w*-?\s?на-?\s?кубани
ru_kda; krymsk; Krymsk; 44.930; 37.990; F; крымск,крымске,крымска
ru_orl; oryol; Oryol; 52.970; 36.060; F; орел,орла,орле,орлом
ru_tul; tula; Tula; 54.190; 37.620; F; тула,тулу,туле,тулы
ru_tul; novomoskovsk_ru; Novomoskovsk (Tula); 54.010; 38.290; F; /новомосковск(?:е|а|у)?(?=\W+(?:тульск|тула))
ru_klu; kaluga; Kaluga; 54.510; 36.260; F; калуг~
ru_mow; moscow; Moscow; 55.760; 37.620; F; москв~
ru_lip; lipetsk; Lipetsk; 52.610; 39.590; F; липецк,липецке,липецка
ru_tam; tambov; Tambov; 52.720; 41.450; F; тамбов,тамбове,тамбова
ru_rya; ryazan; Ryazan; 54.630; 39.740; F; рязан~
ru_smo; smolensk; Smolensk; 54.780; 32.050; F; смоленськ~,смоленск,смоленске,смоленска
ru_smo; shatalovo; Shatalovo; 54.330; 32.470; F; шаталов~
ru_sar; engels; Engels; 51.480; 46.120; F; енгельс~,энгельс~
ru_sar; saratov; Saratov; 51.530; 46.030; F; саратов,саратове,саратова
ru_vgg; volgograd; Volgograd; 48.710; 44.510; F; волгоград,волгограде,волгограда
ru_sta; stavropol; Stavropol; 45.040; 41.970; F; ставрополь,ставрополе,ставрополя
ru_tve; tver; Tver; 56.860; 35.900; F; твер,твери,тверь
ru_yar; yaroslavl; Yaroslavl; 57.630; 39.870; F; ярославл~,ярославль
ru_vlg; cherepovets; Cherepovets; 59.130; 37.900; F; череповц~,череповец
ru_len; kirishi; Kirishi; 59.450; 32.020; F; кириш~
ru_len; ust_luga; Ust-Luga; 59.660; 28.270; F; /усть-?\s?луг\w*
ru_ast; caspian; Caspian Sea; 45.000; 49.000; F; каспі~,каспи~
by; belarus; Belarus; 51.900; 28.000; F; білорус~,беларус~,бєларус~
# ---------------------------------------------------------------- occupied towns in their Russian spelling (Ukrainian territory)
donetsk; horlivka; Horlivka; 48.300; 38.050; T; горлівк~,горлівц~,горловк~
donetsk; makiivka; Makiivka; 48.050; 37.960; T; макіївк~,макіївц~,макеевк~
donetsk; yenakiieve; Yenakiieve; 48.230; 38.210; T; єнакієв~,енакиев~
donetsk; khartsyzk; Khartsyzk; 48.040; 38.150; T; харцизьк~,харцызск~
donetsk; ilovaisk; Ilovaisk; 47.920; 38.200; T; іловайськ~,иловайск~
donetsk; mospyne; Mospyne; 47.880; 38.060; T; моспин~
donetsk; novoazovsk; Novoazovsk; 47.110; 38.080; T; новоазовськ~,новоазовск~
donetsk; volnovakha; Volnovakha; 47.600; 37.500; T; волновах~
donetsk; yasynuvata; Yasynuvata; 48.130; 37.860; T; ясинуват~
donetsk; shakhtarsk; Shakhtarsk; 48.050; 38.450; T; шахтарськ~,шахтерск~
donetsk; debaltseve; Debaltseve; 48.340; 38.400; T; дебальцев~
donetsk; snizhne; Snizhne; 48.030; 38.770; T; сніжн~,снежное,снежном,снежного
donetsk; dokuchaievsk; Dokuchaievsk; 47.750; 37.680; T; докучаєвськ~,докучаевск~
luhansk; alchevsk; Alchevsk; 48.470; 38.800; T; алчевськ~,алчевск~
luhansk; kadiivka; Kadiivka; 48.570; 38.650; T; кадіївк~,стаханов~
luhansk; rovenky; Rovenky; 48.080; 39.370; T; ровеньк~,ровеньки
luhansk; dovzhansk; Dovzhansk; 48.080; 39.650; T; довжанськ~,свердловск~
luhansk; antratsyt; Antratsyt; 48.120; 39.090; T; антрацит~
luhansk; khrustalnyi; Khrustalnyi; 48.140; 38.940; T; /красн\w*\s+луч\w*,хрустальн~
luhansk; shchastia; Shchastia; 48.740; 39.230; T; щаст~,счасть~
luhansk; sorokyne; Sorokyne; 48.300; 39.740; T; краснодон~,сорокин~
luhansk; brianka; Brianka; 48.510; 38.640; T; брянк~
kherson; henichesk; Henichesk; 46.170; 34.800; T; генічеськ~,геническ~
kherson; kalanchak; Kalanchak; 46.250; 33.290; T; каланчак~
kherson; chaplynka; Chaplynka; 46.370; 33.530; T; чаплинк~
zaporizhzhia; prymorsk; Prymorsk; 46.730; 36.350; T; приморськ,приморська,приморську,приморск,приморске,приморска
zaporizhzhia; pryazovske; Pryazovske; 46.730; 35.650; T; приазовськ~,приазовск~
"""

KIND_PROMINENCE = {"C": 3, "T": 2, "D": 2, "F": 2, "R": 1, "W": 1, "V": 1, "A": 2}

OBLAST_NAMES = {
    "vinnytsia": "Vinnytsia", "volyn": "Volyn", "dnipro": "Dnipropetrovsk", "donetsk": "Donetsk",
    "zhytomyr": "Zhytomyr", "zakarpattia": "Zakarpattia", "zaporizhzhia": "Zaporizhzhia",
    "ivano_frankivsk": "Ivano-Frankivsk", "kyiv": "Kyiv region", "kyiv_city": "Kyiv city",
    "kirovohrad": "Kirovohrad", "luhansk": "Luhansk", "lviv": "Lviv", "mykolaiv": "Mykolaiv",
    "odesa": "Odesa", "poltava": "Poltava", "rivne": "Rivne", "sumy": "Sumy", "ternopil": "Ternopil",
    "kharkiv": "Kharkiv", "kherson": "Kherson", "khmelnytskyi": "Khmelnytskyi", "cherkasy": "Cherkasy",
    "chernivtsi": "Chernivtsi", "chernihiv": "Chernihiv", "crimea": "Crimea",
}

UKRAINE_OBLASTS = set(OBLAST_NAMES)

NEIGHBORS = {
    "vinnytsia": ["zhytomyr", "kyiv", "cherkasy", "kirovohrad", "odesa", "khmelnytskyi", "chernivtsi"],
    "volyn": ["rivne", "lviv"],
    "dnipro": ["kharkiv", "donetsk", "zaporizhzhia", "kherson", "mykolaiv", "kirovohrad", "poltava"],
    "donetsk": ["luhansk", "kharkiv", "dnipro", "zaporizhzhia"],
    "zhytomyr": ["kyiv", "vinnytsia", "khmelnytskyi", "rivne"],
    "zakarpattia": ["lviv", "ivano_frankivsk"],
    "zaporizhzhia": ["dnipro", "donetsk", "kherson"],
    "ivano_frankivsk": ["lviv", "ternopil", "chernivtsi", "zakarpattia"],
    "kyiv": ["kyiv_city", "chernihiv", "poltava", "cherkasy", "vinnytsia", "zhytomyr"],
    "kyiv_city": ["kyiv"],
    "kirovohrad": ["cherkasy", "poltava", "dnipro", "mykolaiv", "odesa", "vinnytsia"],
    "luhansk": ["donetsk", "kharkiv"],
    "lviv": ["volyn", "rivne", "ternopil", "ivano_frankivsk", "zakarpattia"],
    "mykolaiv": ["odesa", "kirovohrad", "dnipro", "kherson"],
    "odesa": ["mykolaiv", "kirovohrad", "vinnytsia"],
    "poltava": ["kyiv", "chernihiv", "sumy", "kharkiv", "dnipro", "kirovohrad", "cherkasy"],
    "rivne": ["volyn", "lviv", "ternopil", "khmelnytskyi", "zhytomyr"],
    "sumy": ["chernihiv", "poltava", "kharkiv"],
    "ternopil": ["lviv", "rivne", "khmelnytskyi", "chernivtsi", "ivano_frankivsk"],
    "kharkiv": ["sumy", "poltava", "dnipro", "donetsk", "luhansk"],
    "kherson": ["mykolaiv", "dnipro", "zaporizhzhia", "crimea"],
    "khmelnytskyi": ["rivne", "zhytomyr", "vinnytsia", "chernivtsi", "ternopil"],
    "cherkasy": ["kyiv", "poltava", "kirovohrad", "vinnytsia"],
    "chernivtsi": ["ivano_frankivsk", "ternopil", "khmelnytskyi", "vinnytsia"],
    "chernihiv": ["kyiv", "sumy", "poltava"],
    "crimea": ["kherson"],
}


@dataclass(frozen=True)
class Place:
    key: str
    name: str
    lat: float
    lon: float
    oblast: str
    kind: str

    @property
    def is_region(self) -> bool:
        return self.kind in ("R", "W", "A")

    @property
    def precision(self) -> str:
        return "region" if self.is_region else "point"

    @property
    def prominence(self) -> int:
        return KIND_PROMINENCE.get(self.kind, 1)


@dataclass
class PlaceMatch:
    start: int
    end: int
    candidates: list[Place] = field(default_factory=list)

    @property
    def text_len(self) -> int:
        return self.end - self.start


def _token_to_regex(tok: str) -> str:
    tok = tok.strip()
    if tok.startswith("/"):
        return tok[1:]
    out = []
    for ch in tok:
        if ch == "~":
            out.append(r"\w{0,3}")
        elif ch == "*":
            out.append(r"\w*")
        elif ch == " ":
            out.append(r"\s+")
        elif ch == "'":
            out.append(r"'?")
        elif ch == "-":
            out.append(r"[-\s]?")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def _token_prefixes(tok: str) -> set[str]:
    raw = tok.lstrip("/")
    lit = re.match(r"[a-zа-яіїєґ'\-]+", raw)
    s = lit.group(0) if lit else raw
    variants = {s, s.replace("'", ""), s.replace("-", "")}
    return {v[:3] for v in variants if len(v) >= 3}


REGIONS_FILE = Path(__file__).parent / "data" / "regions.json"
# districts renamed in 2024 (the boundary data uses the 2023 names)
RAION_ALIASES = {"Красноградський": ["Берестинський"], "Новомосковський": ["Самарівський"], "Червоноградський": ["Шептицький"]}


def _raion_tokens(name: str) -> list[str]:
    """'Конотопський' -> Ukrainian and Russian forms of 'Konotop raion' in any case."""
    n = name.lower().replace("’", "'")
    if not n.endswith(("ський", "цький", "зький", "ський")) and not n.endswith("ий"):
        return []
    stem = n[:-2]                                         # конотопськ
    ru = (stem.replace("ськ", "ск").replace("цьк", "цк").replace("зьк", "зск").replace("і", "и").replace("ї", "и")
          .replace("є", "е").replace("'", ""))
    stems = {stem, ru, ru.replace("ив", "ов")}            # Богодухівськ -> Богодуховск
    toks = []
    for st in stems:
        base = st.replace("-", "-")
        toks += [f"{base}~ район*", f"{base}~ р-н*", f"{base}~ р-н.", f"{base}~ районі"]
    return toks


RU_EXTRA = {
    "ru_bel": "бєлгородщин~,белгородчин~,белгородщин~,бєлгородськ~ обл*",
    "ru_krs": "курщин~", "ru_bry": "брянщин~", "ru_vor": "воронежчин~,воронежщин~,воронезьк~ обл*",
    "ru_ros": "ростовщин~", "ru_kda": "кубан~", "ru_mos": "подмосков~,підмосков~", "ru_orl": "орловщин~",
    "ru_klu": "калужчин~,калужин~", "ru_smo": "смоленщин~", "ru_mow": "", "ru_spe": "/санкт-?\\s?петербург\\w*,петербург~,питер~",
    "ru_ta": "татарстан~", "ru_ba": "башкир~,башкортостан~", "ru_kl": "калмык~", "ru_mo": "мордов~", "ru_cu": "чуваш~",
    "ru_ad": "адыге~,адиге~", "ru_kc": "карачаево-черкес~", "ru_kb": "кабардино-балкар~", "ru_se": "/северн\\w*\\s+осети\\w*",
    "ru_ce": "чечн~,чеченск~", "ru_da": "дагестан~", "ru_in": "ингушет~", "ru_me": "/мари\\w*\\s+эл", "ru_kr": "карели~",
    "ru_ko": "/республик\\w*\\s+коми", "ru_ud": "удмурт~",
}


def _russia_tokens(key: str, name: str) -> list[str]:
    """'Брянская обл.' -> брянская/брянской/брянську область...; 'Краснодарский край' -> краснодарск~ кра*."""
    n = name.lower()
    toks = [t for t in RU_EXTRA.get(key, "").split(",") if t]
    m = re.match(r"^([а-яё\-]+?)(?:ая|ий|кий)?\s+(обл\.|край)$", n)
    if m:
        adj = n.split()[0]
        stem = re.sub(r"(ая|ий)$", "", adj)                 # брянск / краснодарск
        kind = "обл*" if n.endswith("обл.") else "кра*"
        ua = stem.replace("ск", "ськ").replace("цк", "цьк")
        toks += [f"{stem}~ {kind}", f"{ua}~ {kind}"]
    return toks


class Gazetteer:
    def __init__(self, data: str = DATA):
        self.places: dict[str, Place] = {}
        self._patterns: dict[str, re.Pattern] = {}
        self._index: dict[str, set[str]] = {}
        self.oblast_center: dict[str, Place] = {}
        for line in data.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(";")]
            if len(parts) != 7:
                raise ValueError(f"bad gazetteer row: {line!r}")
            oblast, key, name, lat, lon, kind, tokens = parts
            place = Place(key, name, float(lat), float(lon), oblast, kind)
            if key in self.places:
                raise ValueError(f"duplicate key {key}")
            self.places[key] = place
            if kind == "R":
                self.oblast_center[oblast] = place
            toks = [t.strip() for t in tokens.split(",") if t.strip()]
            self._add(place, toks)
        self.raions: dict[str, Place] = {}
        if REGIONS_FILE.exists():
            idx = json.loads(REGIONS_FILE.read_text(encoding="utf-8"))
            for r in idx["raions"]:
                toks = _raion_tokens(r["name"])
                for alias in RAION_ALIASES.get(r["name"], ()):
                    toks += _raion_tokens(alias)
                if not toks or r["oblast"] in ("kyiv_city", "sevastopol"):
                    continue
                place = Place("r" + r["id"], f'{r["name_en"]} raion', r["label"][1], r["label"][0], r["oblast"], "A")
                self.places[place.key] = place
                self.raions[r["id"]] = place
                self._add(place, toks)

            for r in idx["russia"]:
                toks = _russia_tokens(r["key"], r["name"])
                place = Place("reg_" + r["key"], r["name"], r["label"][1], r["label"][0], r["key"], "R")
                self.places[place.key] = place
                self.oblast_center[r["key"]] = place
                self._add(place, toks)

    def _add(self, place: "Place", toks: list[str]) -> None:
        if True:
            key = place.key
            alt = "|".join(f"(?:{_token_to_regex(t)})" for t in toks)
            self._patterns[key] = re.compile(rf"(?<![\w'])(?:{alt})(?![\w'])")
            for t in toks:
                for p in _token_prefixes(t.strip()):
                    self._index.setdefault(p, set()).add(key)

    def find(self, text: str) -> list[PlaceMatch]:
        """Return non-overlapping place matches, longest first, in text order."""
        prefixes = set()
        for w in re.findall(r"[\w']+", text):
            for v in (w, w.replace("'", "")):
                if len(v) >= 3:
                    prefixes.add(v[:3])
        keys = set()
        for p in prefixes:
            keys |= self._index.get(p, set())
        spans: dict[tuple[int, int], list[Place]] = {}
        for key in keys:
            for m in self._patterns[key].finditer(text):
                if m.end() > m.start():
                    spans.setdefault((m.start(), m.end()), []).append(self.places[key])
        chosen: list[PlaceMatch] = []
        taken: list[tuple[int, int]] = []
        for (s, e), cands in sorted(spans.items(), key=lambda kv: (-(kv[0][1] - kv[0][0]), kv[0][0])):
            if any(s < te and e > ts for ts, te in taken):
                continue
            taken.append((s, e))
            chosen.append(PlaceMatch(s, e, cands))
        chosen.sort(key=lambda m: m.start)
        return chosen

    @staticmethod
    def resolve(match: PlaceMatch, prefer_oblasts: list[str] | tuple = ()) -> Place:
        if len(match.candidates) == 1:
            return match.candidates[0]
        pref = set(prefer_oblasts)
        return sorted(match.candidates, key=lambda p: (p.oblast not in pref, -p.prominence))[0]


# ---------------------------------------------------------------- geo helpers
R_EARTH = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination(lat: float, lon: float, brg: float, dist_km: float) -> tuple[float, float]:
    d = dist_km / R_EARTH
    b = math.radians(brg)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


GAZETTEER = Gazetteer()
