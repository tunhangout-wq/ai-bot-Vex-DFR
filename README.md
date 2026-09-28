# Vixen Discord EDR Control Center

نظام إدارة Discord فعلي يجمع بين Bot + Dashboard + Economy + Staff + Atria Dawn.

## التشغيل

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

املأ `.env`:

- `DISCORD_TOKEN`
- `OWNER_ID`
- `DASHBOARD_PASSWORD`
- `ATRIA_API_KEY` مضبوط في `.env` لتشغيل Atria Dawn Preview مباشرةً
- `AI_API_KEY` اسم قديم مدعوم للتوافق مع الإصدارات السابقة
- `GUILD_ID` اختياري لتسريع مزامنة Slash Commands لسيرفر محدد

ثم:

```bash
python -m bot.main
```

Dashboard: `http://127.0.0.1:8080` افتراضيًا، أو المنفذ الموجود في `DASHBOARD_PORT` عند التشغيل المحلي.

## Control Center

كل أوامر Control Center التنفيذية متاحة كـ `/slash` وPrefix، وتشمل:

- Server: lockdown/unlockdown, name, icon, verification, slowmode, systemchannel, features
- Channel: create/delete/rename/topic/slowmode/clone/purge/lock/unlock
- Member: timeout/untimeout/kick/ban/unban/deafen/undeafen/mute/unmute/move/dm
- Role: create/delete/add/remove/rename/list
- Security: bans/invites/createinvite/deleteinvite/webhooks/deletewebhooks
- Utility: ping/members/emoji/sticker/event/events/prune/botinfo

الـDashboard يقرأ هذه الأوامر مباشرة من Cog ويعرض معاملات كل أمر ويستدعي نفس callback والصلاحيات، لذلك لا توجد أزرار mock.

## Lockdown

`/server lockdown` يحفظ حالة `@everyone` السابقة لكل قناة ويكمل عند `Forbidden/HTTPException` مع delay صغير لتقليل ضغط Discord. `unlockdown` يستعيد الحالة المحفوظة فقط.

## DM

إرسال DM يحتاج صلاحية Vixen `dm_members` فقط، وليس `moderate_members`. قائمة أعضاء الـDashboard تستخدم pagination بدل حد ثابت 200.

## Staff

`setrank` و`removestaff` يحترمان hierarchy: لا يمكن للعضو منح أو إزالة رتبة مساوية/أعلى من رتبته، والمالك محمي.

## Economy

حد الإضافة اليومي يحسب المبلغ الذي أُضيف فعليًا، مع احترام quota والحدود القصوى للمحفظة والبنك.

## Loans

`/loan` أصبح Hybrid Group: يعمل Slash وPrefix (`!loan request`, `!loan repay`, `!loan my`).

## Atria Dawn

التكامل يستخدم **Atria Dawn Preview مباشرةً** server-side فقط. نقطة الاتصال الرسمية هي `https://api.atria-asi.ai/v1/chat/completions` والموديل هو `Atria-Dawn-Preview` (وحالة الأحرف مهمة). يستخدم الطلب `Authorization: Bearer <ATRIA_API_KEY>`. لا تضع المفتاح في JavaScript أو HTML أو Git.

Dashboard: صفحة Atria AI مع Chat وModeration يدوي وتلقائي قابل للتفعيل.
Bot: `/ai chat`.

يمكن تفعيل moderation من `settings.json` عبر `atria.moderation_enabled`. عند `moderation_mode=all` يفحص الرسائل الجديدة تلقائيًا، وعند `prefix` يفحص الرسائل التي تبدأ بالبادئة المحددة. كما يوجد `/ai moderate` للفحص اليدوي.

## حالة التشغيل على Replit

الـWorkflow يشغل البوت والـDashboard في عملية واحدة. إذا لم يتم ضبط `DISCORD_TOKEN` بعد، يبقى الـDashboard متاحًا في وضع الإعداد بدل أن تنتهي العملية؛ لا يمكن تنفيذ أوامر Discord أو تسجيل دخول المالك حتى تتم إضافة `DISCORD_TOKEN` و`OWNER_ID`.

## التنظيف والاختبار

النسخة النهائية لا تحتوي `__pycache__`, `*.pyc`, `.pytest_cache`, أو ملفات مؤقتة.

قبل التشغيل:

```bash
python -m compileall -q bot
```

ثم شغّل البوت واختبر Slash sync والـDashboard ضد سيرفر Discord فعلي.

## Dashboard command catalog
الـCommand Center يكتشف كل leaf commands من جميع الـCogs (وليس Control فقط) ويعرض المعاملات وينفذ الـcallback الحقيقي مع فحص Vixen permissions. المصدر الحالي يحتوي 117 leaf commands.

## Final Control Center / AI notes
- Dashboard login supports Owner credentials and one-use Vixen staff codes.
- Unbound staff-code sessions use a negative, isolated Dashboard principal; they are never treated as the Discord guild owner.
- Command Center discovers executable leaf commands from all loaded Cogs, not only the Control cog.
- Discord application-command metadata is exposed to the dashboard, including choices; the dashboard renders selects for choices and converts Discord objects such as Member/Role/Channel before invoking the same Cog callback.
- Atria Chat and Atria Moderation use `ATRIA_API_KEY` server-side only (`AI_API_KEY` remains a legacy fallback). Automatic moderation is policy-checked and rate-limited.
- `ZENMUX_API_KEY` is not read by the direct Atria integration. A provider HTTP 401 (for example, “Invalid API key”) means the configured credential was rejected; issue a valid Atria key and set it locally as `ATRIA_API_KEY`. Restart the bot after changing `.env` so the process reloads its configuration. Do not paste credentials into chat or commit them.
- Live Discord Gateway/API validation still requires running the project with a real Discord token, guild ID, and bot permissions.


### AI credentials
ضع مفتاح Atria الجديد في `ATRIA_API_KEY` داخل `.env` المحلي فقط. لا تضع secrets في `.env.example` أو HTML أو JavaScript أو Git. يظل `AI_API_KEY` مدعومًا كاسم قديم للتوافق. يمكن ضبط `ATRIA_API_BASE_URL` لاستخدام endpoint متوافق مع OpenAI؛ لا يُرسل `ZENMUX_API_KEY` تلقائيًا إلى Atria.
## Discord AI message access

AI Chat وAI Moderation يعتمدان على قراءة محتوى الرسائل. في Discord Developer Portal افتح التطبيق → Bot → Privileged Gateway Intents، ثم فعّل **Message Content Intent** واحفظ التغيير. المشروع يطلب هذا الـIntent برمجيًا، لكن Discord يتطلب تفعيله أيضًا من لوحة التطبيق.

من Dashboard: AI Moderation → اختر القنوات وأنواع الكشف والإجراءات → حفظ الإعدادات. ولـAI Chat: اختر القنوات → فعّل AI Chat → اجعل Response Mode = Every Message أو Mention Only حسب السلوك المطلوب → حفظ. الإعدادات تُحفظ في `bot/data/settings.json` داخل قسم `ai` وتُقرأ مباشرة عند وصول الرسالة.
