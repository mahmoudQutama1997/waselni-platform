# نشر وصلني وتثبيت تطبيقات PWA

هذا الدليل يشرح نشر نسخة تجريبية/إنتاجية من منصة وصلني على خدمات مجانية أو منخفضة التكلفة، مع الحفاظ على تطبيق إدارة واحد وخلفية Django واحدة وقاعدة بيانات واحدة.

> لا يحتوي هذا المستودع على نطاق حقيقي. استبدل كل قيمة بين `<...>` بالنطاق أو المعرّف الفعلي لديك. لا تضع أي مفتاح سري أو كلمة مرور داخل كود الواجهة.

## 1. البنية المنشورة

| المكوّن | التقنية | مخرجات البناء | ملاحظات |
| --- | --- | --- | --- |
| الخلفية المشتركة | Django + DRF + Channels/Daphne | `backend/` | REST + WebSocket + قاعدة البيانات |
| تطبيق العميل | React PWA | `frontend/dist/customer` | قابل للتثبيت |
| تطبيق التاجر | React PWA | `frontend/dist/merchant` | قابل للتثبيت |
| تطبيق الكابتن | React PWA | `frontend/dist/captain` | قابل للتثبيت |
| لوحة الإدارة | React (ويب) | `frontend/dist/admin` | تبقى على الويب، تفتح على `/admin` |

كل تطبيق واجهة مستقل: manifest خاص، أيقونات، شاشات بدء، Service Worker، وصفحة عدم اتصال. جميعها تتصل بالخلفية نفسها عبر `VITE_API_URL`.

## 2. متغيرات بيئة الخلفية

انسخ `backend/.env.example` إلى `backend/.env` محليًا. على منصات النشر تُضبط القيم من لوحة التحكم.

| المتغير | إلزامي في الإنتاج | الوصف |
| --- | --- | --- |
| `SECRET_KEY` | نعم | مفتاح عشوائي طويل وفريد. |
| `DEBUG` | نعم | `False` في الإنتاج. |
| `ALLOWED_HOSTS` | نعم | مضيف الخلفية، مثال `waselni-api.onrender.com`. |
| `DATABASE_URL` | نعم | رابط PostgreSQL. |
| `CORS_ALLOWED_ORIGINS` | نعم | روابط تطبيقات الواجهة الأربعة، مفصولة بفواصل. |
| `CSRF_TRUSTED_ORIGINS` | مستحسن | نفس روابط الواجهة (المصادقة JWT لا تعتمد على CSRF، لكنها مطلوبة لأي مسار جلسات). |
| `CORS_ALLOWED_ORIGIN_REGEXES` | اختياري | تعبيرات نمطية إضافية لنشر Vercel المعاين. |
| `REDIS_URL` أو `REDIS_HOST`/`REDIS_PORT` | مستحسن | لتوصيل أحداث WebSocket بين أكثر من عملية/نسخة. بدونها يعمل النظام في الذاكرة داخل عملية واحدة. |
| `SERVE_MEDIA` | حسب الإعداد | `True` عندما يخدم Django ملفات `/media/` بنفسه. |
| `MEDIA_ROOT` | مع قرص دائم | مجلد الصور والوثائق، مثال `/var/data/media`. |
| `SECURE_SSL_REDIRECT` | نعم | `True` خلف HTTPS. |
| `SECURE_HSTS_SECONDS` | مستحسن | يبدأ افتراضيًا بـ 31536000 عند `DEBUG=False`. |
| `RIDE_BASE_FARE`, `RIDE_PRICE_PER_KM`, `RIDE_CHECKPOINT_FEE` | نعم | تسعير الرحلات التجريبي بالشيكل. |
| `BOOTSTRAP_ADMIN_*` | مرة واحدة | لإنشاء أول حساب إدارة عبر `python manage.py bootstrap_admin`. |

مثال `CORS_ALLOWED_ORIGINS`:

```text
https://<customer-app>.vercel.app,https://<merchant-app>.vercel.app,https://<captain-app>.vercel.app,https://<admin-app>.vercel.app
```

أضف نطاقات مخصصة عند ربطها. لا تستخدم `*` مع المصادقة.

## 3. نشر الخلفية على Render

### الطريقة الأولى: Blueprint

1. ارفع المستودع إلى GitHub بعد مراجعة التغييرات.
2. من Render: **New → Blueprint** واختر المستودع.
3. يقرأ Render ملف `render.yaml` الموجود في جذر المستودع وينشئ:
   - خدمة ويب Python باسم `waselni-api`.
   - قاعدة PostgreSQL باسم `waselni-db` (خطة مجانية محدودة المدة).
   - خدمة Key Value (Redis) باسم `waselni-kv` لتوصيل WebSocket بين العمليات.
4. أدخل قيم `CORS_ALLOWED_ORIGINS` و`CSRF_TRUSTED_ORIGINS` و`RIDE_*` عند الطلب.
5. بعد أول نشر، تحقق من:

```bash
curl -i https://<backend-host>/api/health/
```

يجب أن يعيد `200` مع `{"status":"ok","database":"ok"}`. إن أعاد `503` فقاعدة البيانات غير متصلة.

6. أنشئ أول حساب إدارة من Shell الخدمة:

```bash
python manage.py bootstrap_admin
```

أو عيّن متغيرات `BOOTSTRAP_ADMIN_USERNAME` و`BOOTSTRAP_ADMIN_EMAIL` و`BOOTSTRAP_ADMIN_PASSWORD` قبل تشغيل الأمر ثم احذف كلمة المرور من المتغيرات.

### ملاحظات Render المهمة

- خطة الويب المجانية تنام بعد فترة خمول، فينقطع WebSocket مؤقتًا وتستيقظ الخدمة عند أول طلب. التطبيقات تعيد الاتصال تلقائيًا.
- قاعدة PostgreSQL المجانية قد تنتهي صلاحيتها بعد المدة التي تحددها Render؛ انقل البيانات قبل ذلك.
- بدون قرص دائم، تُفقد الصور والوثائق المرفوعة عند إعادة النشر. أضف Disk من نوع Persistent (يتطلب خطة مدفوعة) واضبط `MEDIA_ROOT=/var/data/media`.
- عند تشغيل أكثر من نسخة، يجب وجود Redis/Key Value حتى تصل الأحداث لكل النسخ.
- `collectstatic` غير مطلوب لأن Django لا يخدم ملفات الواجهة؛ الملفات الثابتة تُنشر من Vercel.

### الطريقة الثانية: خدمة يدوية

- Runtime: Python
- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt && python manage.py migrate`
- Start Command: `daphne -b 0.0.0.0 -p $PORT config.asgi:application`
- Health Check Path: `/api/health/`

## 4. نشر التطبيقات الأربعة على Vercel

أنشئ **أربعة مشاريع Vercel منفصلة** من المستودع نفسه:

| المشروع | Root Directory | Build Command | Output Directory |
| --- | --- | --- | --- |
| العميل | `frontend` | `npm run build:customer` | `dist/customer` |
| التاجر | `frontend` | `npm run build:merchant` | `dist/merchant` |
| الكابتن | `frontend` | `npm run build:captain` | `dist/captain` |
| الإدارة | `frontend` | `npm run build:admin` | `dist/admin` |

لكل مشروع:

1. Framework Preset: **Vite** (أو Other مع نفس الأوامر).
2. متغيرات البيئة (Build-time) لكل مشروع:
   - `VITE_API_URL=https://<backend-host>/api`
   - `VITE_WASELNI_APP_ROLE=customer` أو `merchant` أو `captain` أو `admin`
   - `VITE_OSRM_URL=https://router.project-osrm.org`
   - `VITE_GEOCODING_URL=https://nominatim.openstreetmap.org/reverse`
   - `VITE_GEOCODING_SEARCH_URL=https://nominatim.openstreetmap.org/search`
   - `VITE_MAP_TILE_URL` و`VITE_MAP_ATTRIBUTION` حسب مزوّد الخرائط المرخّص لديك.
3. أعد النشر بعد أي تغيير في `VITE_API_URL` لأن Vite يدمج القيم وقت البناء.
4. ملف `frontend/vercel.json` يطبّق توجيه SPA مع استثناءات للأصول وService Worker وmanifest.

بعد النشر تحقق من كل تطبيق:

```bash
curl -I https://<role-app>/manifest.webmanifest
curl -I https://<role-app>/sw.js
curl -I https://<role-app>/icons/icon-192.png
```

يجب أن يعيد `manifest.webmanifest` نوع `application/manifest+json`، و`sw.js` بترويسة `Cache-Control: no-cache`، وألا تُلتقط هذه المسارات عبر إعادة توجيه `index.html`.

### بدائل مجانية

- Netlify أو Cloudflare Pages: استخدم نفس مخرجات `dist/<role>`. ملفات `_headers` و`_redirects` تُولد تلقائيًا داخل كل مجلد مخرجات.
- أي استضافة ثابتة: تأكد من:
  - إعادة توجيه كل المسارات إلى `index.html` ما عدا `/assets`, `/icons`, `/splash`, `/sw.js`, `/manifest.webmanifest`, `/offline.html`.
  - `no-cache` لـ `sw.js` و`index.html`.
  - HTTPS إلزامي (شرط تثبيت PWA وWebSocket الآمن).

## 5. التحقق الوظيفي بعد النشر

1. افتح `/api/health/` وتأكد من `200`.
2. سجّل دخول العميل، أنشئ طلبًا من متجر مفتوح، وتأكد من ظهوره للتاجر.
3. اقبل الطلب كتاجر وحدد وقت التحضير، ثم علّم الطلب جاهزًا.
4. سجّل دخول كابتن معتمد ومشترك نشط، فعّل «متصل»، واستلم الطلب.
5. تحقق من وصول حدث WebSocket فورًا دون تحديث الصفحة.
6. ارفع صورة منتج وصورة متجر ووثيقة كابتن، وتأكد من ظهورها عبر رابط الخلفية (`/media/...`) لا من نطاق Vercel.
7. افتح أدوات المتصفح → Application → Manifest وService Worker: يجب أن يكون التطبيق قابلًا للتثبيت ولا يسجل أخطاء.
8. اقطع الإنترنت وافتح التطبيق: تظهر صفحة عدم الاتصال، ولا تُعرض بيانات طلبات قديمة كأنها حديثة.

## 6. تثبيت التطبيق على iPhone

المتطلب: iOS 16.4 أو أحدث للحصول على أفضل دعم لتطبيقات الويب المثبتة. استخدم **Safari** لأن التثبيت الكامل مدعوم رسميًا عبره.

1. افتح رابط التطبيق في Safari:
   - العميل: `https://<customer-app>`
   - التاجر: `https://<merchant-app>`
   - الكابتن: `https://<captain-app>`
2. اضغط زر المشاركة (مربع يخرج منه سهم) في شريط Safari.
3. مرّر واختر **«إضافة إلى الشاشة الرئيسية»**.
4. اكتب الاسم ثم اضغط **«إضافة»**.
5. افتح التطبيق من الأيقونة الجديدة. يعمل بوضع standalone دون شريط عنوان.
6. بعد أول تفاعل (لمس أي زر) يفعّل التطبيق الصوت؛ اسمح بالإشعارات من زر «الإشعارات» داخل الحساب إن رغبت.

ملاحظات iOS:

- الإشعارات الفورية (Push) للتطبيقات المثبتة تحتاج إعداد Apple ونظام دفع، وغير مفعّلة في هذا الإصدار. ما يعمل هو تنبيه داخل التطبيق وصوت أثناء فتحه فقط.
- تحديد الموقع قد يتوقف عند قفل الشاشة أو ترك التطبيق؛ لا يوجد تتبع GPS في الخلفية.
- لتحديث التطبيق: أغلق التطبيق وافتحه من الأيقونة. عند نشر إصدار جديد يظهر شريط «تحديث» داخل التطبيق.

## 7. تثبيت التطبيق على Android

1. افتح الرابط في Chrome أو Edge على أندرويد.
2. اضغط قائمة النقاط الثلاث.
3. اختر **«تثبيت التطبيق»** أو **«إضافة إلى الشاشة الرئيسية»**.
4. أكّد **«تثبيت»**.
5. افتحه من درج التطبيقات؛ سيظهر كتطبيق WebAPK مستقل.
6. اسمح بالإشعارات والموقع عند طلب التطبيق، بعد أول تفاعل مع الصفحة.

ملاحظات Android:

- الصوت يحتاج تفاعل المستخدم أولًا بسبب سياسات المتصفح.
- الموقع يعمل أثناء فتح التطبيق فقط، وليس في الخلفية.
- التحديث يتم تلقائيًا عند توفر إصدار جديد من Service Worker، مع إمكانية التحديث الفوري من الشريط.

## 8. قيود معروفة يجب عدم إخفائها عن المستخدمين

- **لا إشعارات Push حقيقية**: لا توجد خدمة Firebase أو APNs. الإشعار الفوري يعتمد على WebSocket أثناء فتح التطبيق، مع تنبيه صوتي ونظامي محلي.
- **لا تتبع GPS في الخلفية**: الكابتن يجب أن يبقي التطبيق مفتوحًا لتحديث الموقع.
- **الخدمة المجانية تنام**: أول طلب بعد الخمول قد يتأخر، وتُعاد محاولة الاتصال تلقائيًا.
- **الوسائط غير دائمة افتراضيًا**: بدون قرص دائم أو تخزين كائنات، تُفقد الملفات المرفوعة عند إعادة النشر.
- **الخرائط والعناوين**: الافتراضي خدمات عامة للتجربة. استخدم مزوّدًا مرخّصًا وحدود استخدام مناسبة للإنتاج.
- **الدفع النقدي والتسويات** يحتاجان إجراءات تشغيلية ومراجعة محاسبية قبل الاعتماد الفعلي.
- **لا PWA على سطح المكتب كبديل عن التطبيقات الأصلية**، ولا يوجد ضمان تثبيت من كل المتصفحات المدمجة داخل تطبيقات التواصل.
- اختبر على جهاز حقيقي عبر HTTPS؛ `localhost` لا يمثل سلوك التثبيت أو الموقع على الهاتف.

## 9. الأسرار والأمان

- لا تضع `SECRET_KEY` أو كلمات مرور أو مفاتيح خرائط في `frontend/` أو في Git.
- ملفات `.env` مستثناة من Git؛ ملفات `*.example` فقط هي القوالب.
- استخدم HTTPS دائمًا؛ WebSocket ينتقل تلقائيًا إلى `wss://` عندما يكون عنوان الـ API بـ `https://`.
- رمز الوصول يُرسل عبر WebSocket subprotocol باسم `waselni.jwt.<token>` وليس في رابط الاتصال.
- تسجيل الخروج يمسح رموز الدخول وسلة العميل ويغلق قنوات realtime.
- راجع `SECURITY.md` قبل أي إطلاق حقيقي.
