define([
    'metapolator/errors'
  , 'metapolator/webAPI/window'
  , 'metapolator/webAPI/document'
  , 'metapolator/rendering/glyphBasics'
  , 'metapolator/rendering/dataTransformationCaches/DrawPointsProvider'
  , 'metapolator/rendering/dataTransformationCaches/BBoxProvider'
  , 'metapolator/ui/services/GlyphUIService'
  , 'metapolator/ui/services/DragDataService'
  , 'metapolator/ui/services/DragIndicatorService'
  , 'codemirror/lib/codemirror'
], function(
    errors
  , window
  , document
  , glyphBasics
  , DrawPointsProvider
  , BBoxProvider
  , GlyphUIService
  , DragDataService
  , DragIndicatorService
  , _
) {
    "use strict";

    var CPSParserError = errors.CPSParser
      , CPSError = errors.CPS
      ;

    function RedPill(io, project, angularApp, loadTextEditor) {
        this.angularApp = angularApp;
        this.frontend = undefined;
        this.project = project;
        this.loadTextEditor = loadTextEditor;
        this.drawPointsOutlineProvider = new DrawPointsProvider(glyphBasics.outlinesRenderer);
        this.glyphUIService = new GlyphUIService(document, this.drawPointsOutlineProvider);
        this.dragDataService = new DragDataService();
        this.dragIndicatorService = new DragIndicatorService();

        this.model = {
            masters: this.project.masters
        };
        this._cache = {
            lastSelection: []
        };

        // load all masters, because right now it is very confusing
        // when some masters are missing from the MOM
        this.project.masters.forEach(this.project.open, this.project);


        // will be called on angular.bootstrap
        // see ui/app-controller.js
        this.angularApp.constant('registerFrontend', this._registerFrontend.bind(this));
        this.angularApp.constant('redPillModel', this.model);
        this.angularApp.constant('selectGlyphs', this.selectGlyphs.bind(this));
        this.angularApp.constant('ModelController', this.project.controller);
        this.angularApp.constant('ruleController', this.project.ruleController);
        this.angularApp.constant('glyphUIService', this.glyphUIService);


        // very specific for the cps-panel, right now
        this.angularApp.constant('dragDataService', this.dragDataService);
        this.angularApp.constant('dragIndicatorService', this.dragIndicatorService);
        //end very specific for the cps-panel

        this.angularApp.constant('io', io);
        this.angularApp.constant('config', {loadTextEditor: loadTextEditor});

        this.project.setUpdateChangedRuleHandlers(
            function() {this.frontend.$scope.$broadcast('cpsUpdate');}.bind(this));

    }

    var _p = RedPill.prototype;

    _p._registerFrontend = function(appController) {
        if(this.frontend !== undefined)
            throw new Error('Registering more than one AppController is not allowed.'
                           +' Don\'t use <red-pill> more than once in a template!');
        this.frontend = appController;
    };

    _p._selectGlyphs = function(selector) {
        try {
            return this.project.controller.queryAll(selector)
                .filter(function(item){ return item.type === 'glyph'; });
        }
        catch(error){
            if(!(error instanceof CPSError))
                throw error;
            console.warn('selector "' + selector + '" did not parse:', error.message);
        }
        return false;
    };

    _p.selectGlyphs = function(selector) {
        var result = this._selectGlyphs(selector);
        if(!result)
            return this._cache.lastSelection;
        this._cache.lastSelection = result;
        return result;
    };

    return RedPill;
});
