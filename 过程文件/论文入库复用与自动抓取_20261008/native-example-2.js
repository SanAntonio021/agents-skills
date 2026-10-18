(async function(){
const job = Zotero.__paperDownloadBatches?.jobs["<同一本次UUID>"];
return job ? JSON.parse(JSON.stringify(job)) : null;
})
