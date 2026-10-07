<?php

return [
    'routes' => [
        [
            'name' => 'page#index',
            'url' => '/',
            'verb' => 'GET',
        ],
        [
            'name' => 'api#me',
            'url' => '/api/me',
            'verb' => 'GET',
        ],
        [
            'name' => 'api#health',
            'url' => '/api/health',
            'verb' => 'GET',
        ],
        [
            'name' => 'api#chat',
            'url' => '/api/chat',
            'verb' => 'POST',
        ],
    ],
];