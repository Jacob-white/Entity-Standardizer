"""Small per-country gazetteer of major cities, used ONLY to find where the city starts in a comma-less line.

"6813 Jabal Omar Makkah al Mukarramah 24231" has no street-type word to anchor on and a three-word city; a known city
name at the end of the text before the postal code is the reliable anchor. Lookups are accent-, case- and
hyphen-insensitive. Precision over recall: a name that is not listed is never guessed.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Optional, Tuple

from entity_standardizer.address.international.diacritics import fold_to_ascii_key

_RAW: Dict[Tuple[str, ...], Tuple[str, ...]] = {
    ("ID", "IDN"): (
        "Jakarta", "South Jakarta", "North Jakarta", "East Jakarta", "West Jakarta", "Central Jakarta", "Jakarta Selatan",
        "Jakarta Utara", "Jakarta Timur", "Jakarta Barat", "Jakarta Pusat", "Kota Jakarta Pusat", "Kota Jakarta Selatan",
        "Kota Jakarta Barat", "Kota Jakarta Timur", "Kota Jakarta Utara", "Surabaya", "Bandung", "Medan", "Semarang",
        "Makassar", "Palembang", "Tangerang", "Tangerang Selatan", "Depok", "Bekasi", "Bogor", "Batam", "Pekanbaru",
        "Bandar Lampung", "Malang", "Padang", "Denpasar", "Samarinda", "Balikpapan", "Banjarmasin", "Pontianak",
        "Yogyakarta", "Surakarta", "Solo", "Manado", "Mataram", "Jayapura", "Cimahi", "Cirebon", "Sidoarjo", "Gresik",
        "Kota Bandung", "Kota Surabaya", "Kota Medan", "Kota Semarang", "Kota Malang", "Kota Bogor", "Kota Depok",
        "Kota Bekasi", "Kota Tangerang", "Kota Yogyakarta", "DKI Jakarta", "Kupang", "Ambon", "Palu", "Kendari",
        "Jambi", "Bengkulu", "Banda Aceh", "Serang", "Tasikmalaya", "Kediri", "Perak Barat",
    ),
    ("PH", "PHL"): (
        "Manila", "Quezon City", "Davao City", "Davao", "Cebu City", "Cebu", "Makati", "Makati City", "Taguig",
        "Taguig City", "Pasig", "Pasig City", "Caloocan", "Zamboanga City", "Pasay", "Parañaque", "Mandaluyong",
        "Baguio", "Muntinlupa", "Iloilo City", "Marikina", "Bacolod", "Mandaue", "Lapu-Lapu City", "Angeles",
    ),
    ("IN", "IND"): (
        "Mumbai", "Delhi", "New Delhi", "Bengaluru", "Bangalore", "Hyderabad", "Ahmedabad", "Chennai", "Kolkata",
        "Pune", "Surat", "Jaipur", "Lucknow", "Kanpur", "Nagpur", "Indore", "Thane", "Bhopal", "Visakhapatnam",
        "Patna", "Vadodara", "Ghaziabad", "Ludhiana", "Agra", "Nashik", "Faridabad", "Meerut", "Rajkot", "Varanasi",
        "Srinagar", "Aurangabad", "Dhanbad", "Amritsar", "Navi Mumbai", "Allahabad", "Prayagraj", "Ranchi", "Howrah",
        "Coimbatore", "Jabalpur", "Gwalior", "Vijayawada", "Jodhpur", "Madurai", "Raipur", "Kota", "Chandigarh",
        "Guwahati", "Gurgaon", "Gurugram", "Noida", "Mysore", "Mysuru", "Thiruvananthapuram", "Kochi", "Bhubaneswar",
        "Dehradun", "Mangalore", "Kozhikode", "Panaji", "Shimla", "Jamshedpur", "Salem", "Tiruchirappalli",
    ),
    ("VN", "VNM"): (
        "Hà Nội", "Hanoi", "Hồ Chí Minh", "Thành phố Hồ Chí Minh", "Ho Chi Minh City", "TP. Hồ Chí Minh", "TP.HCM",
        "TPHCM", "Thành phố Thủ Đức", "TP. Thủ Đức", "Thành phố Đà Nẵng", "Đà Nẵng", "Da Nang", "Hải Phòng", "Cần Thơ",
        "Huế", "Nha Trang", "Biên Hòa", "Vũng Tàu", "Đà Lạt", "Hội An", "Thủ Đức", "Quy Nhơn", "Buôn Ma Thuột",
        "Thái Nguyên", "Nam Định", "Hạ Long", "Vinh", "Thanh Hóa", "Hải Dương", "Bắc Ninh", "Thủ Dầu Một",
        "Quận Tây Hồ", "Q.Tây Hồ", "Tây Hồ",
    ),
    ("KE", "KEN"): (
        "Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret", "Thika", "Malindi", "Kitale", "Garissa", "Kakamega",
        "Nyeri", "Machakos", "Meru", "Naivasha", "Kericho", "Kisii", "Lamu", "Embu", "Kiambu", "Ruiru", "Kikuyu",
        "Ngong", "Kajiado", "Nanyuki", "Bungoma", "Busia", "Voi", "Wajir", "Isiolo", "Karen", "Westlands",
    ),
    ("NG", "NGA"): (
        "Lagos", "Abuja", "Kano", "Ibadan", "Port Harcourt", "Benin City", "Kaduna", "Enugu", "Onitsha", "Aba",
        "Jos", "Ilorin", "Abeokuta", "Owerri", "Warri", "Calabar", "Uyo", "Akure", "Maiduguri", "Sokoto", "Zaria",
        "Yola", "Makurdi", "Asaba", "Lokoja", "Osogbo", "Ikeja", "Lekki", "Victoria Island", "Ikoyi",
    ),
    ("SA", "SAU"): (
        "Riyadh", "Jeddah", "Makkah", "Makkah al Mukarramah", "Mecca", "Madinah", "Al Madinah", "Al Madinah al Munawwarah",
        "Medina", "Dammam", "Al Khobar", "AlKhobar", "Al Khubar", "Al Khubar Ash Shamaliyah", "Khobar", "Dhahran",
        "Tabuk", "Buraydah", "Abha", "Khamis Mushait", "Hail", "Najran", "Jazan", "Yanbu", "Al Jubail", "Jubail",
        "Taif", "Al Hofuf", "Hofuf", "Al Qatif", "Qatif",
        "الرياض", "جدة", "مكة المكرمة", "المدينة المنورة", "الدمام", "الخبر", "الخبر الشمالية", "الظهران", "تبوك",
        "بريدة", "أبها", "حائل", "نجران", "جازان", "ينبع", "الجبيل", "الطائف", "الهفوف", "القطيف",
    ),
    ("EG", "EGY"): (
        "Cairo", "Giza", "Alexandria", "New Cairo", "Nasr City", "Maadi", "Heliopolis", "6th of October City",
        "Sheikh Zayed City", "Mansoura", "Tanta", "Port Said", "Suez", "Luxor", "Aswan", "Ismailia", "Zagazig",
        "Damietta", "Fayoum", "Hurghada", "Sharm El Sheikh", "Assiut", "Minya", "Beni Suef", "Sohag", "Qena",
        "القاهرة", "القاهرة الجديدة", "الجيزة", "الإسكندرية", "الاسكندرية", "مدينة نصر", "المعادي", "مصر الجديدة",
        "المنصورة", "طنطا", "بورسعيد", "السويس", "الأقصر", "أسوان", "الإسماعيلية", "الزقازيق", "دمياط", "الفيوم",
        "الغردقة", "أسيوط", "المنيا", "بني سويف", "سوهاج", "قنا", "6 أكتوبر", "الشيخ زايد",
    ),
    ("TH", "THA"): (
        "Bangkok", "Chiang Mai", "Chiang Rai", "Phuket", "Pattaya", "Khon Kaen", "Nakhon Ratchasima", "Udon Thani",
        "Hat Yai", "Nonthaburi", "Samut Prakan", "Surat Thani", "Rayong", "Chonburi", "Nakhon Si Thammarat",
        "Ubon Ratchathani", "Phitsanulok", "Lampang", "Krabi", "Hua Hin", "Ayutthaya", "Nakhon Pathom",
        "กรุงเทพมหานคร", "กรุงเทพ", "เชียงใหม่", "เชียงราย", "ภูเก็ต", "พัทยา", "ขอนแก่น", "นครราชสีมา", "อุดรธานี",
        "หาดใหญ่", "นนทบุรี", "สมุทรปราการ", "สุราษฎร์ธานี", "ระยอง", "ชลบุรี", "นครศรีธรรมราช", "อุบลราชธานี",
        "พิษณุโลก", "ลำปาง", "กระบี่", "หัวหิน", "พระนครศรีอยุธยา", "นครปฐม",
    ),
    ("CO", "COL"): (
        "Bogotá", "Bogotá D.C.", "Bogota", "Medellín", "Cali", "Santiago de Cali", "Barranquilla", "Cartagena",
        "Cartagena de Indias", "Cúcuta", "Bucaramanga", "Pereira", "Santa Marta", "Ibagué", "Manizales", "Pasto",
        "Neiva", "Villavicencio", "Armenia", "Soacha", "Soledad", "Bello", "Itagüí", "Envigado", "Montería", "Popayán",
        "Valledupar", "Sincelejo", "Tunja", "Floridablanca", "Palmira", "Riohacha", "Chía", "Zipaquirá", "Rionegro",
    ),
    ("PE", "PER"): (
        "Lima", "Cercado de Lima", "Arequipa", "Trujillo", "Chiclayo", "Piura", "Iquitos", "Cusco", "Cuzco", "Huancayo",
        "Tacna", "Pucallpa", "Chimbote", "Ica", "Juliaca", "Cajamarca", "Ayacucho", "Puno", "Tarapoto", "Huánuco",
        "San Isidro", "Miraflores", "Surquillo", "Barranco", "San Borja", "Santiago de Surco", "La Molina", "La Victoria",
        "Jesús María", "Lince", "Magdalena del Mar", "San Miguel", "Callao", "Chorrillos", "Pueblo Libre", "Los Olivos",
        "San Martín de Porres", "Comas", "Ate",
    ),
    ("AR", "ARG"): (
        "Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata", "San Miguel de Tucumán", "Tucumán",
        "Mar del Plata", "Salta", "Santa Fe", "San Juan", "Resistencia", "Neuquén", "Santiago del Estero", "Corrientes",
        "Posadas", "Bahía Blanca", "Paraná", "Formosa", "San Luis", "La Rioja", "Catamarca", "Río Cuarto",
        "San Salvador de Jujuy", "Jujuy", "Ushuaia", "Río Gallegos", "Comodoro Rivadavia", "San Carlos de Bariloche",
        "Bariloche", "Trelew", "Rawson", "Viedma", "Santa Rosa", "Tandil", "Quilmes", "Lomas de Zamora", "Lanús",
    ),
    ("CL", "CHL"): (
        "Santiago", "Valparaíso", "Viña del Mar", "Concepción", "Temuco", "Antofagasta", "La Serena", "Rancagua",
        "Talca", "Arica", "Iquique", "Puerto Montt", "Punta Arenas", "Coquimbo", "Osorno", "Valdivia", "Chillán",
        "Calama", "Copiapó", "Los Ángeles", "Curicó", "Providencia", "Las Condes", "Ñuñoa", "Maipú", "Puente Alto",
    ),
    ("UY", "URY"): (
        "Montevideo", "Salto", "Paysandú", "Las Piedras", "Rivera", "Maldonado", "Punta del Este", "Colonia del Sacramento",
        "Tacuarembó", "Melo", "Mercedes", "Artigas", "Minas", "San José de Mayo", "Durazno", "Florida", "Rocha",
    ),
    ("EC", "ECU"): (
        "Quito", "Guayaquil", "Cuenca", "Santo Domingo", "Machala", "Durán", "Manta", "Portoviejo", "Ambato", "Riobamba",
        "Loja", "Esmeraldas", "Ibarra", "Quevedo", "Milagro", "Latacunga", "Babahoyo", "Tulcán",
    ),
    ("BR", "BRA"): (
        "São Paulo", "Sao Paulo", "Rio de Janeiro", "Brasília", "Brasilia", "Salvador", "Fortaleza", "Belo Horizonte",
        "Manaus", "Curitiba", "Recife", "Goiânia", "Goiania", "Belém", "Belem", "Porto Alegre", "Guarulhos", "Campinas",
        "São Luís", "Sao Luis", "São Gonçalo", "Maceió", "Maceio", "Duque de Caxias", "Natal", "Teresina",
        "São Bernardo do Campo", "Campo Grande", "Osasco", "Santo André", "João Pessoa", "Florianópolis",
    ),
    ("MX", "MEX"): (
        "Ciudad de México", "CDMX", "Guadalajara", "Monterrey", "Puebla", "Tijuana", "León", "Leon", "Juárez", "Juarez",
        "Zapopan", "Mérida", "Merida", "Cancún", "Cancun", "Querétaro", "Queretaro", "San Luis Potosí", "Aguascalientes",
        "Hermosillo", "Mexicali", "Culiacán", "Culiacan", "Toluca", "Chihuahua", "Morelia", "Saltillo", "Veracruz",
    ),
    ("ZA", "ZAF"): (
        "Johannesburg", "Cape Town", "Durban", "Pretoria", "Port Elizabeth", "Gqeberha", "Bloemfontein", "East London",
        "Pietermaritzburg", "Nelspruit", "Mbombela", "Kimberley", "Polokwane", "Sandton", "Soweto", "Randburg", "Centurion",
    ),
    ("TR", "TUR"): (
        "İstanbul", "Istanbul", "Ankara", "İzmir", "Izmir", "Bursa", "Antalya", "Adana", "Konya", "Gaziantep",
        "Şanlıurfa", "Sanliurfa", "Kocaeli", "Mersin", "Diyarbakır", "Hatay", "Manisa", "Kayseri", "Samsun",
        "Balıkesir", "Kahramanmaraş", "Van", "Aydın", "Denizli", "Sakarya", "Trabzon", "Kadıköy", "Kadikoy", "Besiktas",
    ),
    ("MY", "MYS"): (
        "Kuala Lumpur", "George Town", "Ipoh", "Johor Bahru", "Petaling Jaya", "Shah Alam", "Malacca City", "Melaka",
        "Kota Kinabalu", "Kuching", "Alor Setar", "Kuantan", "Putrajaya", "Cyberjaya", "Subang Jaya", "Klang",
    ),
    ("PK", "PAK"): (
        "Karachi", "Lahore", "Faisalabad", "Rawalpindi", "Gujranwala", "Peshawar", "Multan", "Islamabad", "Quetta", "Sialkot",
    ),
    ("BD", "BGD"): (
        "Dhaka", "Chittagong", "Chattogram", "Khulna", "Rajshahi", "Sylhet", "Barisal", "Rangpur", "Comilla", "Narayanganj", "Gazipur",
    ),
    ("LK", "LKA"): (
        "Colombo", "Kandy", "Galle", "Jaffna", "Negombo", "Batticaloa", "Trincomalee", "Matara", "Anuradhapura", "Ratnapura",
    ),
    ("MA", "MAR"): (
        "Casablanca", "Rabat", "Fes", "Fès", "Marrakech", "Tangier", "Tanger", "Agadir", "Meknes", "Meknès", "Oujda", "Kenitra", "Tetouan",
    ),
    ("DZ", "DZA"): (
        "Algiers", "Alger", "Oran", "Constantine", "Annaba", "Blida", "Batna", "Djelfa", "Sétif", "Setif", "Sidi Bel Abbès", "Biskra",
    ),
    ("TN", "TUN"): (
        "Tunis", "Sfax", "Sousse", "Kairouan", "Bizerte", "Gabès", "Gabes", "Ariana", "Gafsa", "Monastir", "Ben Arous",
    ),
    ("AE", "ARE"): (
        "Dubai", "Abu Dhabi", "Sharjah", "Al Ain", "Ajman", "Ras Al Khaimah", "Fujairah", "Umm Al Quwain",
    ),
    ("IL", "ISR"): (
        "Jerusalem", "Tel Aviv", "Tel Aviv-Yafo", "Haifa", "Rishon LeZion", "Petah Tikva", "Ashdod", "Netanya", "Beer Sheva", "Holon", "Bnei Brak",
    ),
    ("GH", "GHA"): (
        "Accra", "Kumasi", "Tamale", "Sekondi-Takoradi", "Cape Coast", "Sunyani", "Koforidua", "Tema",
    ),
    ("ET", "ETH"): (
        "Addis Ababa", "Dire Dawa", "Mekelle", "Gondar", "Bahir Dar", "Hawassa", "Jimma", "Dessie", "Jijiga",
    ),
    ("TZ", "TZA"): (
        "Dar es Salaam", "Mwanza", "Arusha", "Dodoma", "Mbeya", "Morogoro", "Tanga", "Zanzibar City", "Zanzibar",
    ),
    ("UG", "UGA"): (
        "Kampala", "Nansana", "Kira", "Mbarara", "Mukono", "Gulu", "Jinja", "Entebbe",
    ),
    ("KZ", "KAZ"): (
        "Almaty", "Astana", "Shymkent", "Karaganda", "Aktobe", "Taraz", "Pavlodar", "Ust-Kamenogorsk", "Semey", "Atyrau",
    ),
    ("UZ", "UZB"): (
        "Tashkent", "Samarkand", "Namangan", "Andijan", "Bukhara", "Nukus", "Fergana", "Qarshi",
    ),
    ("VE", "VEN"): (
        "Caracas", "Maracaibo", "Valencia", "Barquisimeto", "Maracay", "Ciudad Guayana", "San Cristóbal", "Maturín",
    ),
    ("CR", "CRI"): (
        "San José", "San Jose", "Alajuela", "Cartago", "Heredia", "Liberia", "Puntarenas", "Limón", "Limon",
    ),
    ("DO", "DOM"): (
        "Santo Domingo", "Santiago de los Caballeros", "Santiago", "Santo Domingo Este", "Santo Domingo Norte", "Santo Domingo Oeste", "La Romana",
    ),
    ("GT", "GTM"): (
        "Ciudad de Guatemala", "Guatemala City", "Mixco", "Villa Nueva", "Quetzaltenango", "San Miguel Petapa", "Escuintla", "Antigua Guatemala",
    ),
    ("PA", "PAN"): (
        "Ciudad de Panamá", "Panama City", "Panamá", "Panama", "San Miguelito", "Tocumen", "David", "Las Cumbres", "Colón", "Colon", "La Chorrera",
    ),
}

_TABLE: Dict[str, FrozenSet[str]] = {}


def _key(name: str) -> str:
    """Accent-, case-, hyphen- and dot-insensitive form (non-Latin letters kept distinct by the diacritics fold)."""
    return " ".join(fold_to_ascii_key(name.replace("-", " ").replace(".", " ")).split())


for _codes, _names in _RAW.items():
    _keys = frozenset(_key(n) for n in _names)
    for _code in _codes:
        _TABLE[_code] = _keys


def known_city_suffix_length(country_iso: Optional[str], words: "list[str]", max_words: int = 5) -> int:
    """Number of trailing words of ``words`` forming the longest listed city; 0 when none does."""
    keys = _TABLE.get((country_iso or "").upper())
    if not keys:
        return 0
    for n in range(min(max_words, len(words)), 0, -1):
        if _key(" ".join(words[-n:])) in keys:
            return n
    return 0
