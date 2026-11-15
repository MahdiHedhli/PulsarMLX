//! The instants the router hands each handler (`RouteRequest::marks`), added by API-08 for
//! the turn trace of API-07: when the request reached the router, and, for a route whose
//! body the router reads, when the body was read and when it was parsed (the donor's
//! `http`, `body` and `json` marks).

use std::sync::{Arc, Mutex, PoisonError};

use console_http::router::{RequestMarks, Route, RouteHandler, RouteRequest};
use console_http::transport::HandlerFuture;
use console_testkit::server::TestServer;

#[derive(Default)]
struct Seen(Mutex<Vec<RequestMarks>>);

impl RouteHandler for Seen {
    fn serve(&self, mut request: RouteRequest) -> HandlerFuture<'_> {
        Box::pin(async move {
            self.0
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .push(request.marks);
            let _ = request.exchange.responder().json(200, "{}").await;
        })
    }
}

#[tokio::test]
async fn handlers_receive_the_request_marks_in_order() {
    let seen = Arc::new(Seen::default());
    let s = match TestServer::builder()
        .route(Route::ChatCompletions, seen.clone())
        .route(Route::Models, seen.clone())
        .start()
        .await
    {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    let r = s
        .post_json("/v1/chat/completions", &[], "{\"messages\": []}")
        .await;
    assert_eq!(r.status, 200);
    let r = s.get("/v1/models", &[]).await;
    assert_eq!(r.status, 200);
    let marks = seen
        .0
        .lock()
        .unwrap_or_else(PoisonError::into_inner)
        .clone();
    let [chat, models] = marks.as_slice() else {
        panic!("{marks:?}");
    };
    let (Some(body), Some(json)) = (chat.body, chat.json) else {
        panic!("a JSON route has its body marks: {chat:?}");
    };
    assert!(chat.received <= body && body <= json, "{chat:?}");
    // A route whose body the router does not read has none.
    assert_eq!((models.body, models.json), (None, None));
}
