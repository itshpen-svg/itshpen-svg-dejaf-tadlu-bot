# Bot catalog - English names only (avoids encoding issues on deploy).
# Amharic labels stay on the website.

PRODUCTS = [
  {"id": 1, "name": "Yirgacheffe Coffee Beans, 250g", "cat": "Coffee & Tea", "price": 380, "sale": None, "photo": "1.jpg", "desc": "Premium Yirgacheffe coffee beans."},
  {"id": 13, "name": "Amharic Children's Storybook Set", "cat": "Books & Paper", "price": 260, "sale": None, "photo": "13.jpg", "desc": "Three illustrated folktales, printed in Amharic."},
  {"id": 14, "name": "Frankincense & Myrrh Set", "cat": "Home & Garden", "price": 180, "sale": None, "photo": "14.jpg", "desc": "Ethiopian etan resin with a traditional clay burner."},
  { id: 17, name: 'Woven Mesob Basket', cat: 'Home & Garden', price: 1400, sale: null, img: 'photo/17.jpg', desc: 'Handwoven grass basket-table for serving injera.' },
  { id: 19, name: 'Teff Flour, 5kg', cat: 'Grocery', price: 620, sale: null, img: 'photo/19.jpg', desc: 'Whole-grain teff, stone-milled for authentic injera.' },
  { id: 20, name: 'Fresh Avocados, 1kg Bag', cat: 'Grocery', price: 110, sale: null, img: 'photo/20.jpg', desc: 'Locally grown, ready to eat within a day or two.' },
  { id: 21, name: 'Shiro Powder (ሽሮ), 500g', cat: 'Grocery', price: 170, sale: null, img: 'photo/21.jpg', desc: 'Roasted chickpea flour blend, ready for shiro wat.' },
  { id: 22, name: 'Ethiopian Kibe Butter, 250g', cat: 'Grocery', price: 210, sale: null, img: 'photo/22.jpg', desc: 'Spiced clarified butter for traditional dishes.' },
  { id: 29, name: 'Potatoes (ድንች), 1kg', cat: 'Grocery', price: 45, sale: null, img: 'photo/29.jpg', desc: 'Fresh table potatoes, good for wot or frying.' },
  { id: 30, name: 'Carrots (ካሮት), 1kg', cat: 'Grocery', price: 55, sale: null, img: 'photo/30.jpg', desc: 'Crisp, sweet carrots for stews and salads.' },
  { id: 31, name: 'Cabbage (ጎመን), 1 head', cat: 'Grocery', price: 40, sale: null, img: 'photo/31.jpg', desc: 'Fresh green cabbage for atkilt and sides.' },
  { id: 32, name: 'Onions (ሽንኩርት), 1kg', cat: 'Grocery', price: 65, sale: null, img: 'photo/32.jpg', desc: 'Everyday red onions, the base of most wats.' },
  { id: 33, name: 'Garlic (ነጭ ሽንኩርት), 250g', cat: 'Grocery', price: 90, sale: null, img: 'photo/33.jpg', desc: 'Fresh garlic bulbs, sold by the net.' },
  { id: 34, name: 'Tomatoes (ቲማቲም), 1kg', cat: 'Grocery', price: 70, sale: 60, img: 'photo/34.jpg', desc: 'Ripe, ready to cook or slice fresh.' },
  { id: 35, name: 'Cooking Oil (ዘይት), 1L', cat: 'Grocery', price: 260, sale: null, img: 'photo/35.jpg', desc: 'All-purpose vegetable oil for everyday cooking.' },
  { id: 49, name: 'ሳምንታዊ አስቤዛ · Weekly Asbeza', cat: 'Grocery', price: 950, sale: null, img: 'photo/49.jpg', desc: 'Weekly grocery package.' },
  { id: 50, name: 'Beso (በሶ), 1kg', cat: 'Grocery', price: 180, sale: null, img: 'photo/50.jpg', desc: 'Roasted barley flour — classic Ethiopian breakfast and snack staple.' },
  { id: 51, name: 'Aja (አጃ), 1kg', cat: 'Grocery', price: 160, sale: null, img: 'photo/51.jpg', desc: 'Barley grain for porridge, kinche, or home milling.' },
  { id: 52, name: 'Rice (ሩዝ), 1kg', cat: 'Grocery', price: 220, sale: null, img: 'photo/52.jpg', desc: 'Everyday white rice for family meals.' },
  { id: 53, name: 'Qinche (ቅንጨ), 1kg', cat: 'Grocery', price: 170, sale: null, img: 'photo/53.jpg', desc: 'Cracked barley / qinche — ready for traditional porridge.' },
  { id: 54, name: 'Difen Misir (ድፍን ምስር), 1kg', cat: 'Grocery', price: 200, sale: null, img: 'photo/54.jpg', desc: 'Whole red lentils for shiro, stews, and soups.' },
  { id: 55, name: 'Split Misir (ምስር ክክ), 1kg', cat: 'Grocery', price: 210, sale: null, img: 'photo/55.jpg', desc: 'Split red lentils — cooks faster for everyday misir wot.' },
  { id: 56, name: 'Split Ater (አተር ክክ), 1kg', cat: 'Grocery', price: 190, sale: null, img: 'photo/56.jpg', desc: 'Split peas for ater kik wot and hearty stews.' },
  { id: 57, name: 'Peanut Butter (የለውዝ ቅቤ), 500g', cat: 'Grocery', price: 280, sale: null, img: 'photo/57.jpg', desc: 'Smooth peanut butter for bread, snacks, and cooking.' }.
  { id: 23, name: 'Shea Butter Body Cream', cat: 'Beauty & Cosmetics', price: 240, sale: null, img: 'photo/23.jpg', desc: 'Whipped shea butter, unscented, for dry skin.' },
  { id: 24, name: 'Natural Henna Powder, 100g', cat: 'Beauty & Cosmetics', price: 130, sale: null, img: 'photo/24.jpg', desc: 'Pure henna leaf powder for hair and skin art.' },
  { id: 25, name: 'Matte Lipstick Set', cat: 'Beauty & Cosmetics', price: 390, sale: null, img: 'photo/25.jpg', desc: 'Three long-wear shades in a compact travel case.' },
  { id: 41, name: 'Eau de Parfum, For Women', cat: 'Beauty & Cosmetics', price: 950, sale: null, img: 'photo/41.jpg', desc: 'Eau de Parfum for women.' },
  { id: 42, name: 'Eau de Parfum, For Men, 50ml', cat: 'Beauty & Cosmetics', price: 850, sale: null, img: 'photo/42.jpg', desc: 'Eau de Parfum for men, 50ml.' },
  { id: 26, name: 'Voltage Stabilizer, 1000VA', cat: 'Electrical Equipment', price: 1850, sale: null, img: 'photo/26.jpg', desc: 'Protects appliances from Addis Ababa\'s voltage swings.' },
  { id: 27, name: 'LED Bulb Pack, 4 x 9W', cat: 'Electrical Equipment', price: 340, sale: null, img: 'photo/27.jpg', desc: 'Energy-saving daylight bulbs, standard E27 base.' },
  { id: 28, name: 'Rechargeable Emergency Lamp', cat: 'Electrical Equipment', price: 590, sale: null, img: 'photo/28.jpg', desc: 'Backup lighting with a 6-hour runtime, USB charging.' },
  { id: 38, name: 'Kids Pajama Set, Assorted Prints', cat: 'Apparel', price: 480, sale: null, img: 'photo/38.jpg', desc: 'Kids pajama set, assorted prints.' },
  { id: 39, name: 'Kids Pajama Pants, Assorted Prints', cat: 'Apparel', price: 260, sale: null, img: 'photo/39.jpg', desc: 'Kids pajama pants, assorted prints.' },
  { id: 40, name: 'Girls Leggings, Navy & Lilac', cat: 'Apparel', price: 320, sale: null, img: 'photo/40.jpg', desc: 'Girls leggings in navy and lilac.' },
  { id: 43, name: 'Men\'s Pullover Hoodie', cat: 'Apparel', price: 900, sale: null, img: 'photo/43.jpg', desc: 'Men\'s pullover hoodie.' },
  { id: 44, name: 'Men\'s Pique Polo Shirt', cat: 'Apparel', price: 650, sale: null, img: 'photo/44.jpg', desc: 'Men\'s pique polo shirt.' },
  { id: 45, name: 'Men\'s Boxer Shorts, Assorted Patterns (6-Pack)', cat: 'Apparel', price: 780, sale: null, img: 'photo/45.jpg', desc: 'Men\'s boxer shorts, 6-pack.' },
  { id: 46, name: 'Executive Gift Box', cat: 'Gift Packages', price: 3000, sale: null, img: 'photo/46.jpg', desc: 'Executive gift box.' },
  { id: 47, name: 'Birthday Gift Box', cat: 'Gift Packages', price: 3500, sale: null, img: 'photo/47.jpg', desc: 'Birthday gift box.' },
  { id: 48, name: 'Celebration Gift Box', cat: 'Gift Packages', price: 4000, sale: null, img: 'photo/48.jpg', desc: 'Celebration gift set — notebook, bottle/thermos and cards. Custom name available.' },
];

CATEGORIES = sorted(set(p["cat"] for p in PRODUCTS))

