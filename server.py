#!/usr/bin/env python3
"""
RG Display Server: local RS485 controller for R&G LED displays.
Run: python3 server.py [--port 8080] [--serial /dev/...] [--arduino-serial /dev/...] [--rs485-gpio N]

Compatible with Python 3.7+ (Raspberry Pi OS Buster and newer), Linux, macOS and Windows.
"""
import argparse, glob, json, math, os, random, signal, subprocess, sys, threading, time, traceback, unicodedata, uuid
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

try:
    import serial  # pyserial
except ImportError:  # still usable in simulation mode
    serial = None
try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    GPIO = None
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    ZoneInfo = None

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "messages.json")
SETTINGS_FILE = os.path.join(HERE, "settings.json")
HTML_FILE = os.path.join(HERE, "webui.html")
IS_WINDOWS = os.name == "nt"
DEFAULT_SERIAL = None if IS_WINDOWS else "/dev/ttyAMA0"  # Pi UART; Windows has no sensible default

# ---- Clock Data (mirrors clock.hpp) ----
MONTH_PL = ["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"]
NAMEDAYS = [
    "Masław,Mieczysław,Mieczysława,Konkordiusz,Mieszko",
    "Abel,Izydor,Makary,Achacy,Achacjusz",
    "Arletta,Dan,Danisz,Anter,Arleta",
    "Angelika,Aniela,Benedykta,Dobromir,Eugeniusz",
    "Edward,Emilian,Emiliusz,Emiliana,Piotr",
    "Andrzej,Balcer,Baltazar,Jędrzej,Bolemir",
    "Chociesław,Izydor,Julian,Kryspin,Lucjan",
    "Erhard,Mścisław,Seweryn,Heladiusz",
    "Antoni,Bazylissa,Borzymir,Adrian,Bazylisa",
    "Agaton,Dobrosław,Jan,Anna,Hanna",
    "Feliks,Hilary,Honorata,Gracja,Hortensja",
    "Antoni,Arkadiusz,Arkady,Benedykt,Cezaria",
    "Bogumił,Bogusąd,Bogusława,Godfryd,Leoncjusz",
    "Feliks,Hilary,Odo,Amadeusz,Amadea",
    "Aleksander,Dąbrówka,Dobrawa,Domasław,Eligia",
    "Marcel,Waleriusz,Włodzimierz,Piotr,Treweriusz",
    "Antoni,Jan,Rościsław,Alba,Przemił",
    "Bogumił,Jaropełk,Krystyna,Liberata,Lubart",
    "Andrzej,Bernard,Erwin,Adalryk,Alderyk",
    "Dobiegniew,Fabian,Sebastian,Dobrożyźń",
    "Agnieszka,Epifani,Jarosław,Awit,Awita",
    "Anastazy,Dobromysł,Gaudencjusz,Gaudenty,Jutrogost",
    "Emerencja,Ildefons,Jan,Klemens,Maria",
    "Chwalibóg,Felicja,Mirogniew,Chwalibog,Franciszek Salezy",
    "Miłosz,Miłowan,Miłowit,Apollo(n),Artemia",
    "Paula,Paulina,Polikarp,Ksenofont,Leon",
    "Angelika,Ilona,Jan Chryzostom,Adalruna,Alruna",
    "Agnieszka,Augustyn,Flawian,Ildefons,Julian",
    "Franciszek Salezy,Gilda,Hanna,Bartłomiej,Gildas",
    "Adelajda,Feliks,Gerard,Adalgunda,Adelgunda",
    "Cyrus,Euzebiusz,Jan,Eudoksja,Heloiza",
    "Bryda,Brygida,Dobrocha,Emil,Paweł",
    "Joanna,Korneliusz,Maria,Berwin,Ermentruda",
    "Błażej,Hipolit,Hipolita,Ignacy,Klaudyna",
    "Andrzej,Gilbert,Jan,Jędrzej,Częstogoj",
    "Adelajda,Aga,Agata,Albwin,Elpin",
    "Angel,Angelus,Antoni,Amand,Amanda",
    "Romuald,Ryszard,Sulisław,Alfons,Parteniusz",
    "Gniewomir,Gniewosz,Honorat,Ampeliusz,Ampelia",
    "Apolonia,Bernard,Cyryl,Eryk,Eryka",
    "Elwira,Gabriel,Jacek,Apollo(n),Jacenty",
    "Adolf,Adolfa,Adolfina,Bernadeta,Bertrada",
    "Aleksy,Benedykt,Eulalia,Ampeliusz,Ampelia",
    "Benigna,Grzegorz,Jordan,Humbelina,Jordana",
    "Adolf,Adolfa,Adolfina,Auksencjusz,Auksencja",
    "Faustyn,Georgia,Georgina,Jordan,Jordana",
    "Bernard,Dan,Danisz,Daniel,Danuta",
    "Donat,Donata,Franciszek,Julian,Klemens",
    "Albert,Alberta,Albertyna,Agapita,Gertruda",
    "Arnold,Arnolf,Bądzisława,Barbacy,Barbat",
    "Euchariusz,Eustachiusz,Eustachy,Aulus,Leon",
    "Eleonora,Feliks,Fortunat,Gumbert,Henryka",
    "Małgorzata,Nikifor,Piotr,Chociebąd,Konkordia",
    "Bądzimir,Damian,Florentyn,Łazarz,Marta",
    "Bogurad,Bogusz,Boguta,Ermegarda,Irmegarda",
    "Bolebor,Cezary,Konstancjusz,Adam,Antonina",
    "Aleksander,Bogumił,Cezariusz,Dionizy,Gerlinda",
    "Aleksander,Anastazja,Auksencjusz,Achacy,Achacjusz",
    "Chwalibóg,Józef,Makary,Falibog,Gajusz",
    "Albin,Antoni,Antonina,August,Budzisław",
    "Absalon,Franciszek,Halszka,Agnieszka,Helena",
    "Asteriusz,Hieronim,Kunegunda,Gerwin,Gerwina",
    "Adrian,Adrianna,Arkadiusz,Arkady,Jakobina",
    "Adrian,Adrianna,Fryderyk,Jan,Jeremiasz",
    "Eugenia,Felicyta,Frydolin,Będzimysł,Jordan",
    "Felicja,Nadmir,Paweł,Bazyli,Eubul",
    "Beata,Filemon,Jan,Herenia,Julian",
    "Apollo,Dominik,Franciszka,Katarzyna,Mścisława",
    "Aleksander,Bożysław,Cyprian,Gajusz,Kajus",
    "Benedykt,Drogosława,Edwin,Kandyd,Konstanty",
    "Bernard,Blizbor,Grzegorz,Józefina,Piotr",
    "Bożena,Ernest,Ernestyn,Bratomir,Kasjan",
    "Bożeciecha,Jakub,Leon,Afrodyzjusz,Afrodyzy",
    "Gościmir,Heloiza,Klemens,Krzysztof,Longin",
    "Abraham,Cyriak,Henryka,Artemia,Herbert",
    "Gertruda,Harasym,Jan,Agrykola,Gerazym",
    "Aleksander,Anzelm,Boguchwał,Celestyna,Cyryl",
    "Bogdan,Józef,Marek,Markusław,Sybillina",
    "Aleksander,Aleksandra,Ambroży,Anatol,Archip",
    "Benedykt,Filemon,Lubomira,Justynian,Klemencja",
    "Bazylissa,Bogusław,Godzisław,August,Baldwin",
    "Eberhard,Feliks,Katarzyna,Oktawian,Pelagia",
    "Dziersława,Dzierżysława,Gabor,Ademar,Aldmir",
    "Dyzma,Ireneusz,Łucja,Dula,Jozafata",
    "Emanuel,Feliks,Larysa,Bazyli,Emanuela",
    "Benedykt,Ernest,Ernestyn,Jan,Lidia",
    "Aniela,Antoni,Jan,Joanna,Kastor",
    "Cyryl,Czcirad,Eustachiusz,Eustachy,Marek",
    "Amelia,Aniela,Częstobor,Amadeusz,Amadea",
    "Amos,Balbina,Beniamin,Achacy,Achacjusz",
    "Chryzant,Grażyna,Hugo,Hugon,Jakobina",
    "Franciszek,Sądomir,Urban,Laurencja,Miłobąd",
    "Antoni,Cieszygor,Jakub,Pankracy,Ryszard",
    "Ambroży,Bazyli,Benedykt,Izydor,Mira",
    "Borzywoj,Irena,Wincenty",
    "Ada,Adam,Adamina,Celestyn,Celestyna",
    "Donat,Donata,Epifaniusz,Hegezyp,Herman",
    "Apolinary,Cezary,Cezaryna,August,Dionizy",
    "Dobrosława,Dymitr,Maja,Achacy,Achacjusz",
    "Antoni,Apoloniusz,Daniel,Ezechiel,Grodzisław",
    "Filip,Herman,Jaromir,Gemma,Hildebrand",
    "Andrzej,Iwan,Juliusz,Jędrzej,Sabbas",
    "Hermenegild,Hermenegilda,Ida,Długomił,Jan",
    "Berenike,Julianna,Justyn,Ardalion,Justyna",
    "Anastazja,Bazyli,Leonid,Abel,Modest",
    "Benedykt,Bernadetta,Cecyl,Bernadeta,Cecylian",
    "Anicet,Innocenta,Innocenty,Aniceta,Izydor",
    "Apoloniusz,Bogusław,Bogusława,Alicja,Barbara",
    "Adolf,Adolfa,Adolfina,Cieszyrad,Irydion",
    "Agnieszka,Amalia,Czech,Berenika,Czasław",
    "Addar,Anzelm,Bartosz,Apollina,Apollo(n)",
    "Heliodor,Kajus,Leonia,Agapita,Aital",
    "Adalbert,Gerard,Gerarda,Gabriela,Helena",
    "Aleksander,Aleksy,Egbert,Aleksja,Erwin",
    "Jarosław,Marek,Wasyl,Ewodiusz,Ewodia",
    "Artemon,Klaudiusz,Klet,Klarencjusz,Marcelin",
    "Anastazy,Andrzej,Bożebor,Jędrzej,Felicja",
    "Arystarch,Maria,Paweł,Achacy,Achacjusz",
    "Angelina,Augustyn,Bogusław,Ermentruda,Hugo",
    "Bartłomiej,Chwalisława,Eutropiusz,Afrodyzjusz,Afrodyzy",
    "Aniela,Filip,Jakub,Floryna,Jeremi",
    "Afanazy,Anatol,Atanazy,Borys,Walenty",
    "Aleksander,Antonina,Maria,Alodia,Juwenalis",
    "Florian,Grzegorz,January,Antonina,Michał",
    "Irena,Ita,Pius,Penelopa,Stanisław",
    "Benedykta,Benita,Dytrych,Domagniew,Edbert",
    "Benedykt,Bogumir,Domicela,August,Domicjan",
    "Dezyderia,Ilza,Marek,Achacy,Achacjusz",
    "Beatus,Bożydar,Grzegorz,Beat,Karolina",
    "Antonin,Częstomir,Izydor,Chociesław,Gordian",
    "Adalbert,Benedykt,Filip,Franciszek,Iga",
    "Domicela,Domicjan,Dominik,Domicjana,Epifani",
    "Andrzej,Aron,Ciechosław,Agnieszka,Jędrzej",
    "Bończa,Bonifacy,Dobiesław,Ampeliusz,Ampelia",
    "Afanazy,Atanazy,Berta,Cecyliusz,Czcibora",
    "Andrzej,Honorat,Jan Nepomucen,Adam,Jędrzej",
    "Bruno,Herakliusz,Paschalis,Montan,Sławomir",
    "Aleksander,Aleksandra,Alicja,Eryk,Feliks",
    "Augustyn,Celestyn,Iwo,Bernarda,Iwon",
    "Anastazy,Asteriusz,Bazyli,Bazylides,Bernardyn",
    "Donat,Donata,Jan,Krzysztof,Piotr",
    "Emil,Helena,Jan,Julia,Krzesisława",
    "Budziwoj,Dezyderiusz,Dezydery,Emilia,Eufrozyna",
    "Cieszysława,Estera,Jan,Joanna,Maria",
    "Epifan,Grzegorz,Imisława,Beda,Leon",
    "Beda,Filip,Marianna,Adalwin,Adalwina",
    "Beda,Izydor,Jan,Juliusz,Lucjan",
    "Augustyn,German,Jaromir,Emil,Heladiusz",
    "Bogusława,Maksymilian,Maria Magdalena,Ermentruda,Magdalena",
    "Andonik,Feliks,Ferdynand,Andronik,Bazyli",
    "Aniela,Bożysława,Ernesta,Ernestyna,Feliks",
    "Alfons,Alfonsyna,Bernard,Felin,Felina",
    "Efrem,Erazm,Eugeniusz,Domna,Florianna",
    "Cecyliusz,Ferdynand,Klotylda,Karol,Konstantyn",
    "Bazyliusz,Dacjan,Franciszek,Braturad,Gostmił",
    "Bończa,Bonifacy,Dobrociech,Hildebrand,Hildebranda",
    "Benignus,Dominika,Klaudiusz,Kandyda,Laurenty",
    "Antoni,Ciechomir,Jarosław,Anna,Hanna",
    "Karp,Maksym,Medard,Adriana,Medarda",
    "Felicjan,Pelagia,Pelagiusz,Anna,Hanna",
    "Bogumił,Edgar,Małgorzata,Apollo(n),Bogumiła",
    "Anastazy,Barnaba,Feliks,Radomił,Teodozja",
    "Antonina,Bazyli,Jan,Celestyna,Czesław",
    "Antoni,Chociemir,Herman,Lubowid,Lucjan",
    "Bazylid,Bazylis,Eliza,Bazylides,Justyn",
    "Abraham,Angelina,Bernard,Dula,Edburga",
    "Alina,Aneta,Benon,Aubert,Aureusz",
    "Adolf,Adolfa,Adolfina,Adrianna,Awit",
    "Efrem,Elżbieta,Gerwazy,Amand,Amanda",
    "Borzysław,Gerwazy,Julianna,Eurydyka,Grymilda",
    "Bogna,Bogumiła,Bożena,Bratomir,Edburga",
    "Albaniusz,Alicja,Alojza,Alojzy,Chloe",
    "Achacjusz,Achacy,Agenor,Alban,Flawiusz",
    "Agrypina,Albin,Bazyli,Anna,Hanna",
    "Dan,Danisz,Danuta,Emilia,Jan",
    "Albrecht,Eulogiusz,Lucja,Antyd,Dorota",
    "Jan,Jeremi,Jeremiasz,Dawid,Edburga",
    "Maria Magdalena,Władysław,Władysława,Bożydar,Cyryl",
    "Amos,Ireneusz,Józef,Ekard,Heron",
    "Benedykta,Benita,Dalebor,Kasjusz,Paweł",
    "Alpinian,Ciechosława,Cyryl,Bazyli,Emilia",
    "Aaron,Bogusław,Halina,Domicjan,Domicjana",
    "Juda,Maria,Martynian,Bernardyn,Bożydar",
    "Anatol,Jacek,Korneli,Heliodor,Leon",
    "Ageusz,Alfred,Aurelian,Aggeusz,Berta",
    "Antoni,Bartłomiej,Filomena,Jakub,Marta",
    "Agrypina,Chociebor,Dominik,Dominika,Gotard",
    "Antoni,Benedykt,Cyryl,German,Kira",
    "Adrian,Adrianna,Chwalimir,Adolf,Adolfa",
    "Anatolia,Heloiza,Hieronim,Adolfina,Anatola",
    "Aleksander,Amelia,Aniela,Amalberga,Askaniusz",
    "Benedykt,Cyprian,Kalina,Karina,Karyna",
    "Andrzej,Euzebiusz,Feliks,Jędrzej,Epifania",
    "Ernest,Ernestyn,Eugeniusz,Ezdrasz,Henryk",
    "Bonawentura,Damian,Dobrogost,Franciszek,Izabela",
    "Daniel,Dawid,Dawida,Anna,Hanna",
    "Andrzej,Benedykt,Dziersław,Jędrzej,Dzierżysław",
    "Aleksander,Aleksy,Andrzej,Aleksja,Jędrzej",
    "Arnold,Arnolf,Erwin,Arnulf,Matern",
    "Alfred,Arseniusz,Lutobor,Litobor,Marcin",
    "Czech,Czechasz,Czechoń,Czesław,Czesława",
    "Andrzej,Benedykt,Daniel,Jędrzej,Arbogast",
    "Albin,Bolesława,Bolisława,Laurencjusz,Magdalena",
    "Apolinary,Bogna,Żelisław,Apolinaria,Joanna",
    "Antoni,Kinga,Krystyna,Krzesimir,Kunegunda",
    "Jakub,Krzysztof,Nieznamir,Alfons,Dariusz",
    "Anna,Bartolomea,Grażyna,Anita,Hanna",
    "Alfons,Alfonsyna,Aureli,Julia,Laurenty",
    "Innocenta,Innocenty,Marcela,Achacy,Achacjusz",
    "Beatrice,Beatrycze,Beatryks,Cierpisław,Faustyn",
    "Abdon,Julia,Julita,Ludmiła,Maryna",
    "Beatus,Demokryt,Emilian,Adam,Alfonsa",
    "Brodzisław,Justyn,Konrad,Alfons,Justyna",
    "Alfons,Alfonsyna,Borzysława,Edeltruda,Gustaw",
    "August,Augusta,Krzywosąd,Dalmacjusz,Lidia",
    "Alfred,Arystarch,Dominik,Maria,Mironieg",
    "Cyriak,Emil,Karolin,Abel,Maria",
    "Felicysym,Jakub,January,Namir,Stefan",
    "Albert,Alberta,Albertyna,Andromeda,Dobiemir",
    "Cyprian,Cyriak,Cyryl,Dominik,Emilian",
    "Jan,Klarysa,Miłorad,Domicjan,Domicjana",
    "Asteria,Bernard,Bogdan,Amadeusz,Amadea",
    "Aleksander,Herman,Ligia,Lukrecja,Tyburcjusz",
    "Bądzisław,Hilaria,Klara,Bądzsław,Fotyn",
    "Diana,Dianna,Gertruda,Adriana,Helena",
    "Alfred,Atanazja,Dobrowój,Dobrowoj,Dobrowoja",
    "Maria,Napoleon,Stefan,Armida,Arnulf",
    "Alfons,Alfonsyna,Ambroży,Arsacjusz,Domarad",
    "Anastazja,Angelika,Anita,Bertram,Eliza",
    "Agapit,Bogusława,Bronisław,Helena,Ilona",
    "Bolesław,Emilia,Jan,Julian,Juliusz",
    "Bernard,Jan,Sabin,Samuel,Samuela",
    "Adolf,Adolfa,Adolfina,Agapiusz,Baldwin",
    "Cezary,Dalegor,Fabrycjan,Agatonik,Fabrycy",
    "Apolinary,Benicjusz,Filip,Klaudiusz,Laurenty",
    "Bartłomiej,Cieszymir,Jerzy,Anita,Bartosz",
    "Gaudencjusz,Gaudenty,Grzegorz,Arediusz,Elwira",
    "Dobroniega,Joanna,Konstanty,Maksym,Maria",
    "Angel,Angelus,Cezary,Adrianna,Amadeusz",
    "Adelina,Aleksander,Aleksy,Adelinda,Alfons",
    "Flora,Jan,Racibor,Mederyk,Mederyka",
    "Adaukt,Częstowoj,Gaudencja,Miron,Piotr",
    "Bohdan,Paulina,Rajmund,Albertyna,Amat",
    "Bronisław,Bronisława,Bronisz,Anna,Hanna",
    "Absalon,Bohdan,Czech,Adelina,Dionizy",
    "Antoni,Bartłomiej,Bazylissa,Bazylisa,Bronisław",
    "Agatonik,Ida,Lilianna,Bonifacy,Daniela",
    "Dorota,Herakles,Herkulan,Fereol,Herkules",
    "Albin,Beata,Eugenia,Aleksja,Amoniusz",
    "Domasława,Domisława,Marek,Dobrobąd,Gratus",
    "Adrian,Adrianna,Klementyna,Adam,Maria",
    "Augustyna,Aureliusz,Dionizy,Gorgoniusz,Grażyna",
    "Aldona,Łukasz,Mikołaj,Agapiusz,Kandyda",
    "Feliks,Jacek,Jan,Ademar,Dagna",
    "Amadeusz,Amedeusz,Cyrus,Gwidon,Maria",
    "Aleksander,Aureliusz,Eugenia,Amat,Filip",
    "Bernard,Cyprian,Roksana,Matern,Piotr",
    "Albin,Budzigniew,Maria,Ekard,Kamil",
    "Antym,Cyprian,Edda,Edyta,Eufemia",
    "Ariadna,Dezyderiusz,Drogosław,Cherubin,Franciszek",
    "Dobrowit,Irena,Irma,Ariadna,Baltazar",
    "Alfons,Alfonsyna,January,Arnulf,Arnolf",
    "Dionizy,Eustachiusz,Eustachy,Agnieszka,Barbara",
    "Bożeciech,Bożydar,Hipolit,Bernardyna,Ifigenia",
    "Joachim,Joachima,Maurycy,Ignacy,Józefa",
    "Boguchwała,Bogusław,Libert,Elżbieta,Krzysztof",
    "Gerard,Gerarda,Gerhard,Maria,Teodor",
    "Aureli,Aurelia,Aurelian,Ermenfryd,Irmfryd",
    "Cyprian,Euzebiusz,Justyna,Damian,Kacper",
    "Amadeusz,Amedeusz,Damian,Gajusz,Kajus",
    "Jan,Laurencjusz,Luba,Alodiusz,Amalia",
    "Dadźbog,Franciszek,Michalina,Dadzbog,Dadzboga",
    "Grzegorz,Hieronim,Honoriusz,Euzebia,Felicja",
    "Benigna,Cieszysław,Dan,Danuta,Igor",
    "Dionizy,Leodegar,Stanimir,Nasiębor,Teofil",
    "Eustachiusz,Eustachy,Ewald,Augustyna,Cyprian",
    "Edwin,Franciszek,Konrad,Dalewin,Dalwin",
    "Apolinary,Częstogniew,Donat,Charytyna,Faust",
    "Artur,Artus,Bronisław,Alberta,Askaniusz",
    "Amalia,Justyna,Marek,August,Markusław",
    "Artemon,Bryda,Brygida,Demetriusz,Ewodiusz",
    "Arnold,Arnolf,Atanazja,Aaron,Bogdan",
    "Franciszek,German,Kalistrat,Adalryk,Alderyk",
    "Aldona,Brunon,Burchard,Dobromiła,Emil",
    "Cyriak,Eustachiusz,Eustachy,Edwin,Grzymisław",
    "Daniel,Edward,Gerald,Florencjusz,Florenty",
    "Alan,Bernard,Dominik,Fortunata,Gajusz",
    "Brunon,Gościsława,Jadwiga,Sewer,Tekla",
    "Ambroży,Aurelia,Dionizy,Emil,Florentyna",
    "Lucyna,Małgorzata,Marian,Augustyna,Heron",
    "Julian,Łukasz,René,Piotr,Ziemowit",
    "Ferdynand,Fryda,Pelagia,Kleopatra,Paweł",
    "Budzisława,Irena,Jan Kanty,Apollo(n),Aurora",
    "Bernard,Celina,Dobromił,Elżbieta,Hilary",
    "Abercjusz,Filip,Halka,Alodia,Kordian",
    "Iga,Ignacja,Ignacy,German,Giedymin",
    "Antoni,Boleczest,Filip,Marcin,Marek",
    "Bończa,Bonifacy,Chryzant,Daria,Inga",
    "Dymitriusz,Ewaryst,Eweryst,Amand,Amanda",
    "Frumencjusz,Iwona,Sabina,Manfred,Manfreda",
    "Juda,Szymon,Tadeusz,Domabor,Tadea",
    "Euzebia,Franciszek,Longin,Dalia,Ermelinda",
    "Alfons,Alfonsyna,Angel,Edmund,German",
    "Alfons,Alfonsyna,Antoni,Augusta,Godzimir",
    "Andrzej,Konradyn,Konradyna,Jędrzej,Nikola",
    "Ambroży,Bohdana,Bożydar,Agapiusz,Eudoksjusz",
    "Bogumił,Cezary,Chwalisław,German,Hubert",
    "Emeryk,Karol Boromeusz,Mściwój,Agrykola,Dżesika",
    "Blandyn,Blandyna,Dalemir,Florian,Gwidon",
    "Feliks,Leonard,Trzebowit,Daniela,Gabriela",
    "Achilles,Antoni,Engelbert,Amaranta,Florencjusz",
    "Dymitr,Godfryd,Gotfryd,Adrian,Bożydar",
    "Bogudar,Genowefa,Nestor,Joanna,Teodor",
    "Andrzej,Lena,Leon,Jędrzej,Leona",
    "Anastazja,Bartłomiej,Maciej,Jozafat,Marcin",
    "Cibor,Czcibor,Izaak,Arsacjusz,Jonasz",
    "Arkadiusz,Arkady,Brykcjusz,Augustyna,Dalmacjusz",
    "Aga,Agata,Damian,Agryppa,Antyd",
    "Albert,Alberta,Albertyna,Alfons,Artur",
    "Aureliusz,Dionizy,Edmund,Agnieszka,Ariel",
    "Dionizy,Floryn,Grzegorz,Hugo,Jozafat",
    "Aniela,Cieszymysł,Filipina,Gabriela,Galezy",
    "Elżbieta,Mironiega,Paweł,Barbara,Kryspin",
    "Anatol,Edmund,Feliks,Agapiusz,Ampeliusz",
    "Albert,Alberta,Albertyna,Elwira,Heliodor",
    "Cecylia,Marek,Maur,Markusław,Wszemiła",
    "Adela,Erast,Felicyta,Fotyna,Klemens",
    "Dobrosław,Emilia,Emma,Agnieszka,Biruta",
    "Erazm,Jozafat,Katarzyna,Piotr,Tęgomir",
    "Delfin,Dobiemiest,Jan,Konrad,Lechosław",
    "Damazy,Dominik,Leonard,Achacy,Achacjusz",
    "Gościrad,Grzegorz,Jakub,Berta,Ginter",
    "Błażej,Bolemysł,Fryderyk,Klementyna,Paramon",
    "Andrzej,Justyna,Konstanty,Jędrzej,Kutbert",
    "Długosz,Edmund,Eliga,Bianka,Blanka",
    "Adria,Aurelia,Balbina,Bibiana,Budzisław",
    "Franciszek,Kasjan,Ksawery,Atalia,Gerlinda",
    "Barbara,Berno,Biernat,Chrystian,Hieronim",
    "Anastazy,Gerald,Geraldyna,Dalmacjusz,Edyta",
    "Dionizja,Emilian,Jarema,Agata,Angelika",
    "Agaton,Ambroży,Marcin,Józefa,Marcisław",
    "Boguwola,Klement,Maria,Apollo(n),Narcyza",
    "Delfina,Joachim,Joachima,Leokadia,Natasza",
    "Andrzej,Daniel,Judyta,Jędrzej,Brajan",
    "Damazy,Daniela,Julia,Daniel,Stefan",
    "Adelajda,Aleksander,Dagmara,Edburga,Joanna",
    "Lucja,Łucja,Otylia,Aubert,Auksencjusz",
    "Alfred,Arseniusz,Izydor,Heron,Nahum",
    "Celina,Fortunata,Iga,Cecylia,Mścigniew",
    "Adelajda,Ado,Albina,Agrykola,Alina",
    "Florian,Jolanta,Łazarz,Łukasz,Żyrosław",
    "Bogusław,Gracjan,Gracjana,Arkadia,Auksencjusz",
    "Abraham,Beniamin,Dariusz,Bogumiła,Kazimiera",
    "Amon,Bogumiła,Dominik,Dagmara,Liberat",
    "Balbin,Festus,Honorat,Piotr,Temistokles",
    "Beata,Drogomir,Flawian,Franciszka,Gryzelda",
    "Dagobert,Mina,Sławomir,Anatolia,Anatola",
    "Ada,Adam,Adamina,Adela,Druzjanna",
    "Anastazja,Eugenia,Piotr",
    "Dionizy,Szczepan,Wróciwoj,Wrociwoj",
    "Cezary,Fabia,Fabiola,Jan,Krystyna",
    "Antoni,Dobrowiest,Emma,Dobrowieść,Domna",
    "Domawit,Dominik,Gosław,Dawid,Ekard",
    "Dawid,Dawida,Dionizy,Anizja,Egwin",
    "Korneliusz,Mariusz,Melania,Donata,Saturnina",
    "",
]

DAYS_IN_MONTH = [0,31,28,31,30,31,30,31,31,30,31,30,31]

def nameday_index(month, day):
    if month == 2 and day == 29:  # table has no Feb 29; reuse Feb 28
        day = 28
    idx = sum(DAYS_IN_MONTH[m] for m in range(1, month)) + day - 1
    return min(idx, sum(DAYS_IN_MONTH) - 1)

def _nameday_all(now):
    idx = nameday_index(now.month, now.day)
    if 0 <= idx < len(NAMEDAYS):
        return [n.strip() for n in NAMEDAYS[idx].split(",") if n.strip()]
    return []

def short_date(now):
    return f"{now.day} {MONTH_PL[now.month-1]} {now.year}"

def nameday_text(now):
    names = _nameday_all(now)[:5]
    return f"Imieniny: {', '.join(names)}" if names else ""

def nameday_names_only(now):
    return ", ".join(_nameday_all(now))

def nameday_short(now, max_chars=18):
    result = ""
    for name in _nameday_all(now)[:5]:
        candidate = name if not result else result + ", " + name
        if len(candidate) > max_chars:
            break
        result = candidate
    return result

def days_until_end_of_year(now):
    return (datetime(now.year + 1, 1, 1) - now).days

DAYS_PL = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]

def weekday_pl(now):
    return DAYS_PL[now.weekday()].lower()

# ---- Helpers ----
def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        try:
            return int(float(v))
        except (TypeError, ValueError, OverflowError):  # OverflowError: inf
            return default

def _clamp(v, lo, hi, default):
    return max(lo, min(hi, _int(v, default)))

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ---- RS485 frame building ----
FRAME_MAX_TEXT = 0xFF - 12  # length byte = chars + 12, must fit in 2 hex digits
_HEX = "0123456789ABCDEF"

# Characters people type that cp852 lacks; mapped to look-alikes instead of failing.
_TRANSLATE = str.maketrans({
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-",
    "\u201e": '"', "\u201d": '"', "\u201c": '"', "\u201f": '"', "\u2033": '"',
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u2032": "'", "\u00b4": "'",
    "\u2026": "...", "\u00a0": " ", "\u2009": " ", "\u202f": " ",
    "\u20ac": "EUR", "\u2022": "*", "\u00b7": "*",
    # The display font has the degree sign at 0xFF (cp852: NBSP), seen in the original
    # controller's "-- \xffC" temperature field. NBSP typed by users becomes a plain space.
    "\u00b0": "\u00a0",
})

def _cp852_ok(ch):
    try:
        ch.encode("cp852")
        return True
    except UnicodeEncodeError:
        return False

def sanitize_text(text):
    """Make text safe for the display: cp852-encodable, no control bytes, length-capped."""
    out = []
    for ch in str(text).translate(_TRANSLATE):
        if ord(ch) < 32 or ord(ch) == 127:
            out.append(" ")
        elif _cp852_ok(ch):
            out.append(ch)
        else:
            base = unicodedata.normalize("NFKD", ch)[:1]
            out.append(base if base and ord(base) >= 32 and _cp852_ok(base) else "?")
    return "".join(out)[:FRAME_MAX_TEXT]

def _nib(v):
    return ord(_HEX[int(v) & 0xF])

def _hex2(v):
    v = int(v) & 0xFF
    return [_nib(v >> 4), _nib(v)]

def address_bytes(display_number):
    """
    Address as two ASCII hex chars of (n << 2) | 3, left-padded: 29 -> '77', 20 -> '53', 1 -> '07'.
    Source: rg-screens-things issue #1, confirmed by the original controller's dumps
    (it addresses displays 16, 17, 26-29, 40 and 48 this way). Address 0 ('03') is the controller.
    """
    return _hex2(_clamp(display_number, 0, 63, 29) * 4 + 3)

# Frame: 02 | addr(2) | length(2) = payload byte count | payload | checksum(2) | 03
# Payload starts with a 2-char command:
#   "80" set text (+10 control chars + text); the display answers "80" (ACK) to address 0
#   "00" status poll; the display answers "00" + firmware, e.g. "00TLA-2.0a"
CMD_TEXT = (0x38, 0x30)
CMD_POLL = (0x30, 0x30)
CONTROLLER_ADDR = None  # set below (address_bytes needs _hex2)

def build_frame(addr, payload):
    content = list(addr) + _hex2(len(payload)) + list(payload)
    frame = [0x02] + content + _hex2(sum(content) % 256) + [0x03]
    return " ".join("%02X" % b for b in frame)

def parse_frames(buf):
    """Yield (addr_value, payload_bytes) for valid frames in a byte buffer."""
    i = 0
    while True:
        s = buf.find(b"\x02", i)
        if s < 0:
            return
        e = buf.find(b"\x03", s + 1)
        if e < 0:
            return
        s = buf.rfind(b"\x02", s, e)  # resync past a truncated/garbled frame
        body, i = buf[s + 1:e], e + 1
        try:
            if len(body) < 6 or int(body[2:4].decode(), 16) != len(body) - 6:
                continue
            if int(body[-2:].decode(), 16) != sum(body[:-2]) % 256:
                continue
            yield int(body[:2].decode(), 16), bytes(body[4:-2])
        except (ValueError, UnicodeDecodeError):
            continue

def make_message(text, font=3, line=0, alignment=1, x=0, w=96, scroll=0, addr=None, sep=0x37):
    """Build one set-text command as a hex string ("02 .. 03")."""
    if addr is None:
        addr = address_bytes(state.settings.get("display_number", 29))
    data = list(sanitize_text(text).encode("cp852"))
    align = 0 if alignment == 0 else (1 if alignment == 1 else 2)
    # sep (byte 9): 0x37 here, 0x31 in the reference clear; the original controller sends 0x38.
    # Meaning unknown, kept as-is because it is proven to work.
    ctrl = [*CMD_TEXT, _nib(1 if line else 0), _nib(align), sep,
            _nib(_int(font, 1) - 1),
            *_hex2(_clamp(x, 0, 255, 0)), *_hex2(_clamp(w, 0, 255, 96)),
            *_hex2(_clamp(scroll, 0, 255, 0))]
    return build_frame(addr, ctrl + data)

CONTROLLER_ADDR = address_bytes(0)

def clear_frames(addr=None):
    """Blank both lines using reference protocol (byte9=0x31, font=3, 18 spaces)."""
    return [make_message(" " * 18, 3, li, 0, 0, 96, 0, addr=addr, sep=0x31) for li in (0, 1)]

# ---- Display (RS485 port + optional MAX485 direction pin) ----
class Display:
    RETRY_SEC = 10
    READ_TIMEOUT = 0.03

    def __init__(self, path=None, gpio_pin=None):
        self.path = path
        self.gpio_pin = gpio_pin
        self.ser = None
        self.lock = threading.RLock()
        self._next_retry = 0.0
        self.tx_count = 0
        self.last_tx = 0.0
        self.responding = None   # True/False after a status poll, None = not checked yet
        self.firmware = None
        self.checked_at = 0.0
        self._next_check = time.monotonic() + 3
        self.scan_lock = threading.Lock()

    @property
    def connected(self):
        return self.ser is not None

    def open(self, announce=True):
        if not self.path:
            if announce:
                log("No RS485 port configured: SIMULATION MODE (use --serial, e.g. /dev/ttyUSB0 or COM3)")
            return False
        if serial is None:
            if announce:
                log("pyserial not installed: SIMULATION MODE (pip install pyserial)")
            return False
        try:
            # Short read timeout set once and never changed: on Windows every timeout change
            # reconfigures the port, and the CH343 driver then loses the display's reply.
            kw = dict(timeout=self.READ_TIMEOUT, write_timeout=5)
            if not IS_WINDOWS:
                kw["exclusive"] = True  # a second server instance can't share the bus (Windows ports are exclusive anyway)
            try:
                s = serial.Serial(self.path, 9600, **kw)
            except (TypeError, ValueError) as e:
                if "exclusive" not in str(e):
                    raise
                kw.pop("exclusive")  # pyserial < 3.3: "unexpected keyword arguments"
                s = serial.Serial(self.path, 9600, **kw)
            s.rts = False
            time.sleep(0.3)
            self.ser = s
            self.reset_presence()
            log(f"RS485 on {self.path}")
            return True
        except Exception as e:
            if announce:
                log(f"No serial ({e}): SIMULATION MODE, will retry if {self.path} appears")
            return False

    def maybe_reconnect(self):
        if self.ser is not None or not self.path or serial is None:
            return
        now = time.monotonic()
        if now < self._next_retry:
            return
        self._next_retry = now + self.RETRY_SEC
        if port_available(self.path):
            with self.lock:
                self.open(announce=False)

    def close(self):
        with self.lock:
            if self.ser is not None:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None

    def write(self, frame):
        """Send one hex frame string. Never raises; drops to simulation on error."""
        with self.lock:
            if self.ser is None:
                return f"SIM: {frame[:60]}... ({len(frame)} chars)"
            data = bytes.fromhex(frame)
            try:
                if self.gpio_pin is not None:
                    GPIO.output(self.gpio_pin, True)
                self.ser.write(data)
                self.ser.flush()
                if self.gpio_pin is not None:
                    time.sleep(0.002)  # let the last byte leave the shift register
                self.tx_count += 1
                self.last_tx = time.monotonic()
                return f"TX: {frame[:60]}..."
            except Exception as e:
                log(f"RS485 write failed ({e}); reconnecting in background")
                self.close()
                self._next_retry = time.monotonic() + 2
                return f"ERR: {e}"
            finally:
                if self.gpio_pin is not None:
                    try:
                        GPIO.output(self.gpio_pin, False)
                    except Exception:
                        pass

    def query(self, number, payload=CMD_POLL, timeout=0.35):
        """Send a command to display `number` and return its reply payload (str) or None."""
        with self.lock:
            if self.ser is None:
                return None
            wait = self.last_tx + 0.05 - time.monotonic()
            if wait > 0:
                time.sleep(wait)  # let the display finish ACKing our last frame (half duplex)
            try:
                self.ser.reset_input_buffer()  # drop ACKs of earlier text frames
            except Exception:
                pass
            if not self.write(build_frame(address_bytes(number), payload)).startswith("TX"):
                return None
            ser, buf = self.ser, b""
            deadline = time.monotonic() + timeout
            try:
                while time.monotonic() < deadline:
                    buf += ser.read(max(1, ser.in_waiting))
                    for a, data in parse_frames(buf):
                        # Replies go to the controller (address 0) and echo the command code;
                        # this skips a late "80" ACK of an earlier text frame.
                        if a == 3 and data[:2] == bytes(payload[:2]):
                            return data.decode("cp852", errors="replace")
            except Exception as e:
                log(f"RS485 read failed ({e})")
                return None
            return None

    def reset_presence(self):
        """Forget the last poll result and check again shortly (new port or display number)."""
        self.responding, self.firmware = None, None
        self._next_check = time.monotonic() + 1

    def check_presence(self, number, every=30):
        """Poll the configured display now and then; tells "port open" from "display answers"."""
        if self.ser is None or time.monotonic() < self._next_check:
            return
        self._next_check = time.monotonic() + every
        reply = self.query(number)
        was = self.responding
        self.responding = bool(reply and reply.startswith("00"))
        self.checked_at = time.time()
        if self.responding:
            self.firmware = reply[2:] or None
        if was is not self.responding:
            log(f"Display {number}: " + (f"answers (firmware {self.firmware})" if self.responding
                                          else "no reply to status poll (no power/wiring, wrong number, or adapter can't receive)"))

    def scan(self, numbers, timeout=0.25):
        found = []
        for n in numbers:
            reply = self.query(n, timeout=timeout)
            if reply is not None:
                found.append({"number": n, "reply": reply,
                              "firmware": reply[2:] if reply.startswith("00") else None})
        return found

    def send(self, frames, gap_ms=100, blank=False):
        """Send a full update as one bus transaction (optional blank first)."""
        logs = []
        with self.lock:
            if blank:
                for f in clear_frames():
                    self.write(f)
                    time.sleep(0.05)
                time.sleep(0.05)
            for f in frames:
                logs.append(self.write(f))
                if len(frames) > 1:
                    time.sleep(gap_ms / 1000.0)
        return "; ".join(logs)

# ---- Presets ----
PART_KEYS = ("text", "font", "line", "align", "x", "w", "scroll")

def expand_preset(msg, now):
    """
    Expand a message dict into a list of (text, font, line, align, x, w, scroll) tuples.
    Text may contain __placeholders__ that fill_dynamic() resolves.
    """
    preset = msg.get("preset_id", "custom")
    g = msg.get
    gi = lambda k, d: _int(g(k, d), d)
    gs = lambda k: str(g(k) or "")
    parts = []

    if preset == "scrolling":
        return [(gs("text"), gi("font", 1), gi("line", 0), gi("alignment", 1),
                 gi("pos_x", 0), gi("width", 96), gi("scroll", 99))]

    if preset == "single-static":
        return [(gs("text"), gi("font", 1), gi("line", 0), gi("alignment", 0),
                 gi("pos_x", 0), gi("width", 96), 0)]

    if preset == "two-static":
        lines = gs("text").split("||")
        if len(lines) >= 1 and lines[0].strip():
            parts.append((lines[0].strip(), gi("font", 1), 0, gi("alignment", 0), 0, 96, 0))
        if len(lines) >= 2 and lines[1].strip():
            parts.append((lines[1].strip(), gi("_ts_font2", 1), 1, gi("_ts_align2", 0), 0, 96, 0))
        return parts

    if preset == "bus":
        # Route (font 3, left) + dest (font 1, same line) + scrolling (L1).
        # Digit widths: '1'=4px, others=6px, 1px gap between chars.
        route, dest, scroll_txt = gs("text"), gs("name"), gs("_scroll")
        shift = gi("_bus_shift", 0)
        if route:
            w = sum(4 if c == '1' else 6 for c in route) + max(0, len(route) - 1)
            dest_x = max(6, min(60, 2 + w + 2 + shift))
            parts.append((route, 3, 0, 0, 2, dest_x - 1, 0))
        else:
            dest_x = 6
        if dest:
            parts.append((dest, 1, 0, 0, dest_x, 96, 0))
        if scroll_txt:
            parts.append((scroll_txt, 1, 1, 2, dest_x, 96, gi("scroll", 99)))
        return parts

    if preset == "train":
        # From (L0) + to (L1) + number (L0 right, font 5). Number: 4px/digit + 1px gaps.
        from_st, to_st, number = gs("text"), gs("_train_to"), gs("name")
        f_from, f_to = gi("_train_font_from", 1), gi("_train_font_to", 1)
        a_from, a_to = gi("_train_align_from", 0), gi("_train_align_to", 2)
        if number:
            nw = len(number) * 5 - 1
            num_x = max(20, min(80, 84 - nw + gi("_train_shift", 0)))
            if from_st:
                parts.append((from_st, f_from, 0, a_from, 2, num_x, 0))
            if to_st:
                parts.append((to_st, f_to, 1, a_to, 0, num_x, 0))
            parts.append((number, 5, 0, 0, num_x, 96, 0))
        else:
            if from_st:
                parts.append((from_st, f_from, 0, a_from, 2, 96, 0))
            if to_st:
                parts.append((to_st, f_to, 1, a_to, 0, 96, 0))
        return parts

    if preset == "top-bottom-scroll":
        top, bottom = gs("text"), gs("_tbs_bottom")
        if top:
            parts.append((top, gi("_tbs_font_top", 1), 0, 1, 0, 96, 0))
        if bottom:
            parts.append((bottom, gi("_tbs_font_bottom", 1), 1, 1, 0, 96, gi("_tbs_scroll", 99)))
        return parts

    if preset == "clock":
        # Time (font 3, left) + date (font 1, right) + weekday (font 1, line 1, under date)
        time_str = now.strftime("%H:%M")
        time_width = sum(4 if c == '1' else (2 if c == ':' else 6) for c in time_str) + len(time_str) - 1
        time_right = max(6, min(60, 2 + time_width + 2 + gi("_clock_shift", 0)))
        parts.append(("__clock_time__", 3, 0, 0, 2, time_right, 0))
        date_x = time_right + 4
        parts.append(("__clock_date__", 1, 0, 0, date_x, 96, 0))
        f1_pw = lambda t: 4 * len(t)
        weekday_x = date_x + max(0, (f1_pw(short_date(now)) - f1_pw(weekday_pl(now))) // 2)
        parts.append(("__clock_weekday__", 1, 1, 0, weekday_x, 96, 0))
        return parts

    if preset == "imieniny":
        parts.append(("IMIENINY", 2, 0, 1, 0, 96, 0))
        parts.append(("__imieniny_names__", 1, 1, 1, 0, 96, gi("_imieniny_scroll", 99)))
        return parts

    if preset == "dht22":
        dht = sensor.snapshot()
        parts.append((f"Temp: {dht['temp']} st.", 1, 0, 1, 0, 96, 0))
        if dht["ok"]:
            parts.append((f"Wilg: {dht['hum']} pct.", 1, 1, 1, 0, 96, 0))
        else:
            parts.append(("Brak czujnika", 1, 1, 1, 0, 96, 0))
        return parts

    if preset == "imieniny-static":
        parts.append(("IMIENINY", 2, 0, 1, 0, 96, 0))
        names = nameday_short(now, 18)
        if names:
            parts.append((names, 1, 1, 1, 0, 96, 0))
        return parts

    if preset == "imieniny-scroll":
        return [(f"Imieniny: {nameday_names_only(now)}", 1, 0, 1, 0, 96, 99)]

    if preset in ("do-konca-roku", "do-konca-roku-scroll"):
        count = days_until_end_of_year(now)
        dni = "dzień" if count == 1 else "dni"
        if preset == "do-konca-roku-scroll":
            return [(f"Do końca roku pozostało {count} {dni}", 1, 0, 1, 0, 96, 99)]
        if g("_dkr_split", False):
            return [("Do końca roku", 2, 0, 1, 0, 96, 0),
                    (f"pozostało {count} {dni}", 1, 1, 1, 0, 96, 0)]
        return [("Do końca roku pozostało", 1, 0, 1, 0, 96, 0),
                (f"{count} {dni}", 1, 1, 1, 0, 96, 0)]

    # custom / unknown preset
    return [(gs("text"), gi("font", 1), gi("line", 0), gi("alignment", 0),
             gi("pos_x", 0), gi("width", 96), gi("scroll", 0))]

def fill_dynamic(text, now):
    """Resolve __placeholders__ (works in any text, kept for compatibility)."""
    if text == "__clock_time__":
        return now.strftime("%H:%M")
    if text == "__clock_date__":
        return short_date(now)
    if text == "__clock_weekday__":
        return weekday_pl(now)
    if text == "__imieniny_names__":
        return nameday_names_only(now)
    if text == "__dynamic__":
        return " "
    return text

def preset_parts(msg, now=None):
    """Expanded parts with placeholders filled and text sanitized (what the display gets)."""
    now = now or now_dt()
    out = []
    for text, font, line, align, x, w, scroll in expand_preset(msg, now):
        t = fill_dynamic(text, now)
        if t == "" and text.startswith("__"):
            t = " "
        out.append((sanitize_text(t), font, line, align, x, w, scroll))
    return out

def parts_to_frames(parts):
    return [make_message(*p) for p in parts]

def preset_frames(msg, now=None):
    return parts_to_frames(preset_parts(msg, now))

def parts_json(parts):
    return [dict(zip(PART_KEYS, p)) for p in parts]

# ---- DHT22 sensor (Arduino over serial: "T:23.5 H:45" lines, or "ERR") ----
class Sensor:
    STALE_SEC = 60

    def __init__(self):
        self.lock = threading.Lock()
        self.port = None
        self.temp = "--.-"
        self.hum = "--"
        self._ok = False
        self.updated = 0.0

    def snapshot(self):
        with self.lock:
            ok = self._ok and time.monotonic() - self.updated < self.STALE_SEC
            return {"temp": self.temp, "hum": self.hum, "ok": ok}

    def set_reading(self, temp, hum):
        with self.lock:
            first = not self._ok
            self.temp, self.hum, self._ok = temp, hum, True
            self.updated = time.monotonic()
        if first:
            log(f"DHT22: {temp}C {hum}%")

    def set_error(self):
        with self.lock:
            self._ok = False

sensor = Sensor()

def arduino_reader(port_path):
    if serial is None:
        log("pyserial not installed: DHT22 reader disabled")
        return
    sensor.port = port_path
    log(f"Arduino reader: connecting to {port_path} ...")
    last_err = None
    while state.running:
        try:
            with serial.Serial(port_path, 9600, timeout=2) as ser:
                log(f"Arduino DHT22 on {port_path}")
                last_err = None
                sensor.set_error()
                while state.running:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("T:") and " H:" in line:
                        try:
                            p = line.split()
                            temp_s, hum_s = p[0][2:], p[1][2:]
                            if math.isfinite(float(temp_s)) and math.isfinite(float(hum_s)):
                                sensor.set_reading(temp_s, hum_s)
                            else:  # DHT library prints "nan" when a read fails
                                sensor.set_error()
                        except (ValueError, IndexError):
                            pass
                    elif line == "ERR":
                        sensor.set_error()
        except Exception as e:
            sensor.set_error()
            if str(e) != last_err:  # don't spam the log while unplugged
                log(f"Arduino serial error: {e}")
                last_err = str(e)
            time.sleep(5)

# ---- State ----
DEFAULT_SETTINGS = {
    "display_number": 29,
    "preset_gap_ms": 100,
    "keepalive_sec": 60,
    "queue_running": True,
    "random_mode": False,
}
# key -> (type, min, max); unknown keys are kept as-is for compatibility
SETTING_SPECS = {
    "display_number": (int, 0, 63),
    "preset_gap_ms": (int, 10, 2000),
    "keepalive_sec": (int, 0, 3600),
    "queue_running": (bool, None, None),
    "random_mode": (bool, None, None),
}

def _empty_override():
    return {"active": False, "message": {}, "expires_at": 0}

class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.running = False
        self.messages = []
        self.settings = dict(DEFAULT_SETTINGS)
        self.override = _empty_override()
        self.ov_seq = 0          # bumps on every override change
        self.version = 0         # bumps on every message list change (UI refetch hint)
        self.current = None      # what the engine is showing (slot dict)
        self.queue_pos = 0       # 1-based position of the current queue message
        self.force_next = False
        self.pending_skip = None
        self.last_frames = None
        self.last_parts = None
        self.last_preset = None
        self.last_sent = 0.0
        self.held = None         # "clear"/"test" while the display shows something else
        self.time_offset = 0.0   # system clock minus browser clock (seconds)
        self.synced_at = 0
        self.tz = None
        self.tz_name = None
        self.display = Display()

    def next_id(self):
        ids = {m.get("id") for m in self.messages}
        while True:
            i = uuid.uuid4().hex[:8]
            if i not in ids:
                return i

    def touch(self):
        self.version += 1
        self.wake.set()

state = State()

# ---- Time (browser sync corrects a Pi without RTC/NTP) ----
def now_ts():
    return time.time() - state.time_offset

def now_dt():
    tz = state.tz
    if tz is not None:
        return datetime.fromtimestamp(now_ts(), tz).replace(tzinfo=None)
    return datetime.fromtimestamp(now_ts())

def utc_offset_min():
    ts = now_ts()
    return int(round(((now_dt() - datetime(1970, 1, 1)).total_seconds() - ts) / 60.0))

# ---- Persistence (atomic writes; a corrupt file is kept aside, never overwritten) ----
def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(5):
        try:
            os.replace(tmp, path)
        except PermissionError:  # Windows: target briefly open by an editor/antivirus
            if attempt == 4:
                raise
            time.sleep(0.1)
        else:
            break
    _fsync_dir(os.path.dirname(os.path.abspath(path)))

def _fsync_dir(d):
    """Make a rename in directory `d` durable (POSIX only; Windows can't open directories)."""
    if os.name == "nt":
        return
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def _quarantine(path, err):
    bad = f"{path}.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        os.replace(path, bad)
        log(f"Failed to load {path}: {err}; moved it to {bad}")
    except OSError:
        log(f"Failed to load {path}: {err}")

def save_data():
    with state.lock:
        data = {"messages": state.messages}
        try:
            _atomic_write_json(DATA_FILE, data)
        except OSError as e:
            log(f"Failed to save {DATA_FILE}: {e}")

def load_data():
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        msgs = data.get("messages", []) if isinstance(data, dict) else data
        if not isinstance(msgs, list):
            raise ValueError("'messages' is not a list")
    except Exception as e:
        _quarantine(DATA_FILE, e)
        return
    seen, out = set(), []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if not isinstance(m.get("id"), str) or not m["id"] or m["id"] in seen:
            m["id"] = uuid.uuid4().hex[:8]
        seen.add(m["id"])
        out.append(m)
    state.messages = out
    log(f"Loaded {len(out)} messages from {DATA_FILE}")

def coerce_settings(new, base):
    """Merge validated values from `new` into a copy of `base`. Returns (merged, errors)."""
    out, errors = dict(base), []
    for k, v in new.items():
        spec = SETTING_SPECS.get(k)
        if spec is None:
            out[k] = v
            continue
        typ, lo, hi = spec
        if typ is bool:
            if isinstance(v, str):
                v = v.strip().lower() in ("1", "true", "yes", "on")
            out[k] = bool(v)
        else:
            iv = _int(v, None)
            if iv is None or isinstance(v, bool):
                errors.append(f"{k}: not a number")
                continue
            out[k] = max(lo, min(hi, iv))
    return out, errors

def save_settings():
    with state.lock:
        try:
            _atomic_write_json(SETTINGS_FILE, state.settings)
        except OSError as e:
            log(f"Failed to save {SETTINGS_FILE}: {e}")

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            raise ValueError("not an object")
    except Exception as e:
        _quarantine(SETTINGS_FILE, e)
        return
    state.settings, _ = coerce_settings(saved, state.settings)
    log(f"Loaded settings from {SETTINGS_FILE}")

# ---- Display engine (the only place that drives the queue) ----
def is_visible(m, t):
    if m.get("hidden"):
        return False
    sched = m.get("schedule") or {}
    if isinstance(sched, dict) and sched.get("enabled"):
        f, to = _int(sched.get("from_ts"), 0), _int(sched.get("to_ts"), 0)
        if f and t < f:
            return False
        if to and t > to:
            return False
    return True

def _find(mid):
    for i, m in enumerate(state.messages):
        if m.get("id") == mid:
            return i
    return None

def _pick_next(t, cur_idx, cur_id):
    msgs = state.messages
    n = len(msgs)
    visible = [i for i, m in enumerate(msgs) if is_visible(m, t)]
    if not visible:
        return None
    if state.settings.get("random_mode"):
        choices = [i for i in visible if msgs[i].get("id") != cur_id] or visible
        return random.choice(choices)
    start = 0 if cur_idx is None else cur_idx
    for k in range(n):
        i = (start + k) % n
        if i in visible:
            return i
    return visible[0]

def _queue_slot(i, t, explicit=False):
    m = state.messages[i]
    return {"key": ("queue", m.get("id"), t), "source": "queue", "id": m.get("id"),
            "index": i, "msg": m, "since": t,
            "until": t + max(1, _int(m.get("duration_sec", 10), 10)), "explicit": explicit}

def _needs_blank(preset, old_parts, new_parts):
    if old_parts is None or preset != state.last_preset:
        return True
    if preset == "clock":
        # Same heuristic as before: only blank when the hour's first digit/length changes.
        old_t, new_t = old_parts[0][0], new_parts[0][0]
        return not (old_t and new_t and old_t[0] == new_t[0] and len(old_t) == len(new_t))
    return [p[1:] for p in old_parts] != [p[1:] for p in new_parts]

def tick():
    t = now_ts()
    blank_only = False
    with state.lock:
        ov = state.override
        exp = _int(ov.get("expires_at"), 0)
        if ov.get("active") and exp and t >= exp:
            log("Override expired")
            state.override = ov = _empty_override()
            state.ov_seq += 1
            state.force_next = True
        cur = state.current
        want, new_slot, force = None, False, False
        q_running = state.settings.get("queue_running", True)

        if ov.get("active") and isinstance(ov.get("message"), dict) and ov["message"]:
            key = ("override", state.ov_seq)
            if cur and cur["key"] == key:
                want = cur
            else:
                want = {"key": key, "source": "override", "id": None, "index": None,
                        "since": t, "until": exp, "explicit": True}
                new_slot = force = True
            want["msg"] = ov["message"]
        elif state.pending_skip is not None:
            i = _find(state.pending_skip)
            state.pending_skip = None
            if i is not None:
                want, new_slot, force = _queue_slot(i, t, explicit=True), True, True
        if want is None and not new_slot:
            cur_q = cur if cur and cur["source"] == "queue" else None
            idx = _find(cur_q["id"]) if cur_q else None
            if q_running or state.force_next:
                m = state.messages[idx] if idx is not None else None
                advance = (state.force_next or m is None or t >= cur_q["until"]
                           or (m.get("hidden") and not cur_q["explicit"]))
                state.force_next = False
                if advance:
                    if idx is not None:
                        start = idx + 1
                    elif cur_q is not None:
                        start = cur_q["index"]  # deleted: whatever slid into its place
                    else:
                        start = max(0, state.queue_pos)  # after override / at startup
                    nxt = _pick_next(t, start % max(1, len(state.messages)) if state.messages else None,
                                     cur_q["id"] if cur_q else None)
                    if nxt is None:
                        blank_only = cur is not None
                        state.current = None
                    else:
                        want, new_slot = _queue_slot(nxt, t), True
                else:
                    want = cur_q
                    want["msg"], want["index"] = m, idx
            elif cur_q is not None and idx is not None:
                want = cur_q  # paused: keep refreshing what's on screen
                want["msg"], want["index"] = state.messages[idx], idx

        if want is not None:
            state.current = want
            if want["source"] == "queue":
                state.queue_pos = want["index"] + 1
            msg = want["msg"]
        gap = _int(state.settings.get("preset_gap_ms", 100), 100)
        keepalive = _int(state.settings.get("keepalive_sec", 0), 0)

    if blank_only:
        state.display.send([], blank=True)
        state.last_frames = state.last_parts = state.last_preset = None
        state.held = None
        return
    if want is None:
        return

    parts = preset_parts(msg)
    frames = parts_to_frames(parts)
    preset = msg.get("preset_id", "custom")
    want["parts"] = parts
    if new_slot:
        send = force or state.held or frames != state.last_frames
        blank = True
    elif frames != state.last_frames:
        send, blank = True, _needs_blank(preset, state.last_parts, parts)
    else:
        send = (keepalive > 0 and not state.held
                and time.monotonic() - state.last_sent >= keepalive
                and all(p[6] == 0 for p in parts))
        blank = False
    if send:
        state.display.send(frames, gap, blank=blank)
        state.last_frames, state.last_parts, state.last_preset = frames, parts, preset
        state.last_sent = time.monotonic()
        state.held = None

def display_loop():
    while state.running:
        try:
            state.display.maybe_reconnect()
            state.display.check_presence(_int(state.settings.get("display_number", 29), 29))
            tick()
        except Exception:
            log("Display loop error (continuing):\n" + traceback.format_exc())
            time.sleep(1)
        state.wake.wait(0.5)
        state.wake.clear()

# ---- HTTP ----
class BadRequest(Exception):
    pass

def _reject_constant(name):
    raise ValueError(f"{name} is not allowed")  # NaN / Infinity would poison numeric fields

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Clients dropping the connection (phones switching apps, ConnectionAbortedError on
        # Windows) are normal; don't fill the log with tracebacks for them.
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError, OSError)):
            return
        super().handle_error(request, client_address)
    # On Windows SO_REUSEADDR lets a second server bind the same port silently; avoid that.
    allow_reuse_address = not IS_WINDOWS

_html_cache = {"mtime": None, "body": b""}

def load_html():
    try:
        mtime = os.path.getmtime(HTML_FILE)
        if mtime != _html_cache["mtime"]:
            with open(HTML_FILE, "rb") as f:
                _html_cache["body"] = f.read()
            _html_cache["mtime"] = mtime
    except OSError as e:
        if _html_cache["mtime"] is None:
            _html_cache["body"] = f"<h1>webui.html missing</h1><p>{e}</p>".encode()
    return _html_cache["body"]

def status_payload():
    with state.lock:
        cur = state.current
        current = None
        if cur:
            m = cur.get("msg") or {}
            current = {
                "source": cur["source"], "id": cur.get("id"), "index": cur.get("index"),
                "preset_id": m.get("preset_id", "custom"), "since": cur.get("since"),
                "until": cur.get("until") or 0, "parts": parts_json(cur.get("parts") or []),
            }
        dht = sensor.snapshot()
        return {
            "ok": True,
            "display_connected": state.display.connected,
            "display_port": state.display.path,
            "display_responding": state.display.responding,
            "display_firmware": state.display.firmware,
            "queue_running": state.settings.get("queue_running", True),
            "queue_position": state.queue_pos,
            "messages_count": len(state.messages),
            "override_active": bool(state.override.get("active")),
            "override_message": state.override.get("message", {}),
            "override_expires_at": state.override.get("expires_at", 0),
            "time_synced": state.synced_at > 0,
            "settings": state.settings,
            "dht22_temp": dht["temp"],
            "dht22_hum": dht["hum"],
            "dht22_ok": dht["ok"],
            "sensor_port": sensor.port,
            "current": current,
            "held": state.held,
            "version": state.version,
            "server_time": now_ts(),
            "utc_offset_min": utc_offset_min(),
            "tz": state.tz_name,
        }

class Handler(BaseHTTPRequestHandler):
    server_version = "RGDisplay/2"
    timeout = 30  # socket timeout: a stalled client can't hold a thread forever

    def log_request(self, code="-", size="-"):
        # Keep the log (and the Pi's SD card) quiet: only log changes and errors.
        if self.command in ("GET", "HEAD", "OPTIONS") and str(code)[:1] in ("2", "3"):
            return
        super().log_request(code, size)

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _html(self):
        self._send(200, load_html(), "text/html; charset=utf-8")

    def _body(self, want=dict):
        n = _int(self.headers.get("Content-Length", 0), 0)
        if n > 1_000_000:
            raise BadRequest("body too large")
        raw = self.rfile.read(n) if n > 0 else b""
        if not raw.strip():
            return want()
        try:
            data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        except (ValueError, UnicodeDecodeError) as e:
            raise BadRequest(f"invalid JSON: {e}")
        if not isinstance(data, want):
            raise BadRequest(f"expected a JSON {'object' if want is dict else 'array'}")
        return data

    def _id(self):
        mid = parse_qs(urlparse(self.path).query).get("id", [None])[0]
        if not mid:
            raise BadRequest("missing id")
        return mid

    def _dispatch(self, routes):
        p = urlparse(self.path).path.rstrip("/") or "/"
        fn = routes.get(p)
        try:
            if fn is None:
                if self.command in ("GET", "HEAD") and not p.startswith("/api/"):
                    return self._html()
                return self._json({"error": "not found"}, 404)
            fn()
        except BadRequest as e:
            self._json({"error": str(e)}, 400)
        except (ConnectionError, TimeoutError):  # includes BrokenPipe/Reset/Aborted (Windows)
            pass
        except Exception as e:
            log("Request error:\n" + traceback.format_exc())
            try:
                self._json({"error": f"internal error: {e}"}, 500)
            except Exception:
                pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        # Don't add X-RG-Confirm here: leaving it out is what blocks cross-site /api/poweroff.
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self._dispatch({
            "/": self._html,
            "/api/status": lambda: self._json(status_payload()),
            "/api/messages": self.get_messages,
            "/api/settings": lambda: self._json(state.settings),
            "/api/override": lambda: self._json(state.override),
        })

    do_HEAD = do_GET

    def do_POST(self):
        self._dispatch({
            "/api/messages": self.create_message,
            "/api/messages/reorder": self.reorder,
            "/api/test": self.test,
            "/api/discover": self.discover,
            "/api/override": self.set_override,
            "/api/cancel-override": self.cancel_override,
            "/api/clear": self.clear,
            "/api/time": self.sync_time,
            "/api/skip-to-message": self.skip_to,
            "/api/next": self.next_message,
            "/api/preview": self.preview,
            "/api/poweroff": self.poweroff,
        })

    def do_PUT(self):
        self._dispatch({"/api/messages": self.update_message, "/api/settings": self.update_settings})

    def do_DELETE(self):
        self._dispatch({"/api/messages": self.delete_message})

    # -- messages --
    def get_messages(self):
        with state.lock:  # snapshot only; never write to the socket while holding the lock
            data = {"messages": list(state.messages), "version": state.version}
        self._json(data)

    def create_message(self):
        msg = self._body()
        with state.lock:
            if not isinstance(msg.get("id"), str) or not msg["id"] or _find(msg["id"]) is not None:
                msg["id"] = state.next_id()
            state.messages.append(msg)
            save_data()
            state.touch()
        self._json(msg, 201)

    def update_message(self):
        mid, b = self._id(), self._body()
        with state.lock:
            i = _find(mid)
            if i is None:
                return self._json({"error": "not found"}, 404)
            b["id"] = mid
            state.messages[i] = b
            save_data()
            state.touch()
        self._json(b)

    def delete_message(self):
        mid = self._id()
        with state.lock:
            state.messages = [m for m in state.messages if m.get("id") != mid]
            save_data()
            state.touch()
        self._json({"ok": True})

    def reorder(self):
        ids = self._body().get("ids", [])
        if not isinstance(ids, list):
            raise BadRequest("ids must be a list")
        with state.lock:
            lookup = {m.get("id"): m for m in state.messages}
            ordered = [lookup.pop(i) for i in ids if i in lookup]
            # Messages missing from `ids` (e.g. added by another client meanwhile) are kept.
            state.messages = ordered + [m for m in state.messages if m.get("id") in lookup]
            save_data()
            state.touch()
        self._json({"ok": True})

    def skip_to(self):
        mid = self._id()
        with state.lock:
            i = _find(mid)
            if i is None:
                return self._json({"error": "not found"}, 404)
            if state.override.get("active"):
                state.override = _empty_override()
                state.ov_seq += 1
            state.pending_skip = mid
            state.wake.set()
        self._json({"ok": True, "index": i})

    def next_message(self):
        with state.lock:
            state.force_next = True
            state.wake.set()
        self._json({"ok": True})

    # -- override --
    def set_override(self):
        b = self._body()
        msg = b.get("message") or {}
        if not isinstance(msg, dict):
            raise BadRequest("message must be an object")
        ov = dict(b)
        ov["message"] = msg
        ov["active"] = bool(b.get("active")) and bool(msg)
        exp = _int(b.get("expires_at"), 0)
        if _int(b.get("expires_in"), 0) > 0:
            exp = int(now_ts()) + _int(b["expires_in"], 0)
        ov["expires_at"] = exp
        ov.pop("expires_in", None)
        with state.lock:
            state.override = ov
            state.ov_seq += 1
            state.pending_skip = None  # a skip queued just before must not fire after the override
            if not ov["active"]:
                state.force_next = True
            state.wake.set()
        self._json(ov)

    def cancel_override(self):
        with state.lock:
            state.override = _empty_override()
            state.ov_seq += 1
            state.force_next = True
            state.wake.set()
        self._json({"ok": True})

    # -- display --
    def poweroff(self):
        # Custom header forces a CORS preflight, and do_OPTIONS doesn't allow it, so a
        # random web page on the LAN can't trigger this; only same-origin requests can.
        if self.headers.get("X-RG-Confirm", "").strip().lower() != "poweroff":
            return self._json({"error": "missing X-RG-Confirm: poweroff header"}, 403)
        log("Power off requested via API")
        save_data()
        save_settings()
        if hasattr(os, "sync"):
            os.sync()
        self._json({"ok": True})

        def run():
            time.sleep(1)
            cmd = ["sudo", "-n", "/usr/bin/systemctl", "poweroff"]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if r.returncode != 0:
                    log(f"Power off failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()}")
            except (OSError, subprocess.SubprocessError) as e:
                log(f"Power off failed: {e}")
        threading.Thread(target=run, daemon=True).start()

    def clear(self):
        state.display.send([], blank=True)
        state.held = "clear"
        self._json({"ok": True})

    def test(self):
        with state.lock:
            n = state.settings.get("display_number", 29)
        frames = preset_frames({"text": f"TEST {n}", "font": 3, "line": 0, "alignment": 1,
                                "pos_x": 0, "width": 96, "scroll": 0, "preset_id": "single-static"})
        r = state.display.send(frames, 100)
        state.held = "test"
        self._json({"result": r})

    def discover(self):
        b = self._body()
        lo, hi = _clamp(b.get("from", 1), 0, 63, 1), _clamp(b.get("to", 63), 0, 63, 63)
        disp = state.display
        if not disp.connected:
            return self._json({"result": "Simulation mode: no RS485 port to scan", "found": []})
        if not disp.scan_lock.acquire(blocking=False):
            return self._json({"error": "a scan is already running"}, 409)
        try:
            log(f"Scanning displays {lo}-{hi} ...")
            found = disp.scan(range(lo, hi + 1))
        finally:
            disp.scan_lock.release()
        names = ", ".join(f"{f['number']}" + (f" ({f['firmware']})" if f["firmware"] else "") for f in found)
        result = f"Found: {names}" if found else f"No display answered on {lo}-{hi}"
        log(result)
        self._json({"result": result, "found": found})

    def preview(self):
        b = self._body()
        msg = b.get("message") if isinstance(b.get("message"), dict) else b
        parts = preset_parts(msg)
        self._json({"parts": parts_json(parts), "frames": len(parts)})

    # -- settings / time --
    def update_settings(self):
        b = self._body()
        with state.lock:
            old_number = state.settings.get("display_number")
            state.settings, errors = coerce_settings(b, state.settings)
            save_settings()
            if state.settings.get("display_number") != old_number:
                state.display.reset_presence()
            state.wake.set()
            data = state.settings if not errors else dict(state.settings, _errors=errors)
        self._json(data)

    def sync_time(self):
        b = self._body()
        ts = b.get("unix_seconds", 0)
        if not isinstance(ts, (int, float)) or isinstance(ts, bool) or ts <= 0:
            return self._json({"ok": True})
        if not 946684800 <= ts <= 4102444800:  # 2000..2100; anything else would break every clock calculation
            raise BadRequest("unix_seconds out of range")
        offset = time.time() - float(ts)
        tz, tz_name = None, None
        name = b.get("tz")
        if isinstance(name, str) and name and ZoneInfo is not None:
            try:
                tz, tz_name = ZoneInfo(name), name
            except Exception as e:
                tz = None
                log(f"Time zone {name!r} not available ({e}); using a fixed UTC offset"
                    + (". On Windows: pip install tzdata" if IS_WINDOWS else ""))
        off_min = b.get("tz_offset_min")
        if tz is None and isinstance(off_min, (int, float)) and not isinstance(off_min, bool) and -1440 < off_min < 1440:
            tz = timezone(timedelta(minutes=b["tz_offset_min"]))
            tz_name = f"UTC{b['tz_offset_min'] / 60:+g}"
        with state.lock:
            state.time_offset = offset if abs(offset) >= 2 else 0.0
            state.synced_at = float(ts)
            if tz is not None:
                state.tz, state.tz_name = tz, tz_name
            state.wake.set()
        log(f"Time synced: {now_dt():%Y-%m-%d %H:%M:%S} (offset {offset:+.1f}s, tz {tz_name or 'system'})")
        self._json({"ok": True, "offset": state.time_offset, "tz": state.tz_name})

# ---- Serial port detection (--auto / --list-ports; used by start.sh and start.bat) ----
def _same_port(a, b):
    norm = lambda p: p.replace("\\\\.\\", "").lower() if IS_WINDOWS else p
    return norm(a) == norm(b)

def port_available(path):
    """Whether a serial port exists now. COM ports aren't files, so ask pyserial on Windows."""
    if not path:
        return False
    if os.path.exists(path):
        return True
    if serial is None:
        return False
    try:
        from serial.tools import list_ports
        return any(_same_port(p.device, path) for p in list_ports.comports())
    except Exception:
        return False

def list_serial_ports():
    """[(device, description)] of ports that could be the RS485 adapter or the Arduino."""
    if serial is not None:
        try:
            from serial.tools import list_ports
            out = []
            for p in sorted(list_ports.comports(), key=lambda p: p.device):
                base = os.path.basename(p.device)
                if sys.platform == "darwin" and base.startswith("tty."):
                    continue  # macOS lists cu.* and tty.* for each device; cu.* is the one to open
                if not IS_WINDOWS and p.vid is None and not base.startswith("ttyAMA"):
                    continue  # skip built-in/Bluetooth/virtual ports; keep USB and the Pi UART
                desc = " ".join(x for x in (p.manufacturer, p.product or p.description)
                                if x and x != "n/a" and x != p.device)
                out.append((p.device, desc))
            return out
        except Exception:
            pass
    pats = (["/dev/cu.usbmodem*", "/dev/cu.usbserial*"] if sys.platform == "darwin"
            else ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*"])
    return [(d, "") for pat in pats for d in sorted(glob.glob(pat))]

def auto_detect(args, ports=None, interactive=None, ask=input):
    """Fill in args.serial / args.arduino_serial / args.rs485_gpio, asking when there's a terminal."""
    if interactive is None:
        interactive = sys.stdin is not None and sys.stdin.isatty()
    say = lambda m: print(m, file=sys.stderr, flush=True)

    def prompt(question, default):
        if not interactive:
            return default
        try:
            return (ask(question) or "").strip() or default
        except EOFError:
            return default

    pi_auto = False
    if (args.serial is None and sys.platform.startswith("linux") and GPIO is not None
            and os.path.exists("/dev/ttyAMA0")):
        say("Raspberry Pi detected with RPi.GPIO.")
        args.serial, pi_auto = "/dev/ttyAMA0", True
        say(f"RS485: {args.serial} (auto)")
        if args.rs485_gpio is None:
            args.rs485_gpio = 26
            say(f"RS485 GPIO: pin {args.rs485_gpio} (auto)")

    taken = [p for p in (args.serial, args.arduino_serial) if p]
    devs = [d for d in (list_serial_ports() if ports is None else ports)
            if not any(_same_port(d[0], t) for t in taken)
            and not (pi_auto and os.path.basename(d[0]).startswith("ttyAMA"))]
    show = lambda d: f"{d[0]}  {d[1]}".rstrip()

    def pick(question):
        say(question)
        for i, d in enumerate(devs, 1):
            say(f"  [{i}] {show(d)}")
        c = prompt(f"Choose [1-{len(devs)}] or 0 for none: ", "0")
        if c.isdigit() and 1 <= int(c) <= len(devs):
            return devs.pop(int(c) - 1)[0]
        return None

    if devs and not interactive and (args.serial is None or args.arduino_serial is None):
        say(f"Not interactive: skipping device prompts (found: {', '.join(d[0] for d in devs)}). "
            "Use --serial / --arduino-serial.")
    elif devs:
        if args.serial is None:
            if len(devs) == 1:
                say(f"Single serial device found: {show(devs[0])}")
                role = prompt("Is it the [R]S485 display interface or the DHT22 [A]rduino? ", "R")
                if role[:1].lower() == "a":
                    args.arduino_serial = devs[0][0]
                else:
                    args.serial = devs[0][0]
                devs.clear()
            else:
                args.serial = pick("Which device is the RS485 display interface?")
        if args.arduino_serial is None and len(devs) == 1:
            yn = prompt(f"Use {devs[0][0]} as the DHT22 Arduino? [Y/n]: ", "Y")
            if yn[:1].lower() != "n":
                args.arduino_serial = devs[0][0]
        elif args.arduino_serial is None and len(devs) > 1:
            args.arduino_serial = pick("Which device is the DHT22 Arduino?")

    if args.serial is None:
        say("No RS485 interface selected: " + (f"server tries its default {DEFAULT_SERIAL}, else SIMULATION MODE."
                                               if DEFAULT_SERIAL else "SIMULATION MODE."))
        say("Pass --serial ... to use a specific device.")
    else:
        say(f"RS485:   {args.serial}")
    if args.arduino_serial:
        say(f"Arduino: {args.arduino_serial}")

def setup_console():
    """Log Polish text safely even when output goes to a non-UTF-8 file or pipe (e.g. on Windows)."""
    for s in (sys.stdout, sys.stderr):
        try:
            if (s.encoding or "").lower().replace("-", "") != "utf8":
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

def main():
    ap = argparse.ArgumentParser(description="RG Display Server")
    ap.add_argument("--port", default=8080, type=int)
    ap.add_argument("--bind", default="0.0.0.0", help="Address to listen on (default 0.0.0.0)")
    ap.add_argument("--serial", default=None,
                    help=f"RS485 display port, e.g. /dev/ttyUSB0 or COM3 (default: {DEFAULT_SERIAL or 'none, simulation'})")
    ap.add_argument("--arduino-serial", default=None, help="Serial port for DHT22 Arduino")
    ap.add_argument("--rs485-gpio", type=int, default=None, help="BCM GPIO pin tied to MAX485 RE+DE for direction control")
    ap.add_argument("--auto", action="store_true",
                    help="Detect serial ports and ask which is which (what start.sh / start.bat use)")
    ap.add_argument("--list-ports", action="store_true", help="List detected serial ports and exit")
    args = ap.parse_args()
    setup_console()

    if args.list_ports:
        ports = list_serial_ports()
        for dev, desc in ports:
            print(f"{dev}  {desc}".rstrip())
        if not ports:
            print("No serial ports found" + ("" if serial is not None else " (pyserial not installed)"))
        return
    if args.auto:
        auto_detect(args)
    if args.serial is None:
        args.serial = DEFAULT_SERIAL

    load_data()
    load_settings()

    # Bind first: if the port is taken (another instance?), stop before touching the bus.
    try:
        srv = ThreadingHTTPServer((args.bind, args.port), Handler)
    except OSError as e:
        log(f"Can't listen on {args.bind}:{args.port} ({e}). Is another instance running? Try --port.")
        sys.exit(1)

    disp = Display(args.serial)
    if args.rs485_gpio is not None:
        if GPIO is not None:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(args.rs485_gpio, GPIO.OUT, initial=GPIO.LOW)
            disp.gpio_pin = args.rs485_gpio
            log(f"RS485 GPIO direction on pin {args.rs485_gpio}")
        else:
            log("Warning: RPi.GPIO not available, --rs485-gpio ignored")
    disp.open()
    state.display = disp
    state.running = True

    if args.arduino_serial:
        threading.Thread(target=arduino_reader, args=(args.arduino_serial,), daemon=True).start()
    else:
        log("No Arduino sensor (use --arduino-serial, e.g. /dev/ttyACM0 or COM4, for DHT22)")

    log(f"WebUI: {HTML_FILE} ({len(load_html())} bytes)")
    threading.Thread(target=display_loop, daemon=True).start()

    def _term(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _term)

    log(f"Server: http://localhost:{args.port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.running = False
        state.wake.set()
        save_data()
        disp.close()
        if disp.gpio_pin is not None:
            GPIO.cleanup()
        srv.server_close()
        log("Stopped")

if __name__ == "__main__":
    main()
