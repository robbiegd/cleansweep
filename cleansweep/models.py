import itertools
from flask.ext.sqlalchemy import SQLAlchemy
from .app import app

db = SQLAlchemy(app)

class PlaceType(db.Model):
    """There are different types of places in the hierarchy like
    country, state, region etc. This table captures that.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    short_name = db.Column(db.Text, nullable=False, unique=True)

    # number to indicate level of the type. For example:
    # 10 for country
    # 20 for state
    # 30 for region
    # etc.
    level = db.Column(db.Integer, nullable=False)

    def __init__(self, name, short_name, level):
        self.name = name
        self.short_name = short_name
        self.level = level

    def __repr__(self):
        return '<%s>' % self.short_name

    def get_subtype(self):
        return PlaceType.query.filter(PlaceType.level > self.level).order_by(PlaceType.level).first()

    @staticmethod
    def get(short_name):
        """Returns PlaceType object with given short_name.
        """
        return PlaceType.query.filter_by(short_name=short_name).first()

    @staticmethod
    def all():
        return PlaceType.query.order_by(PlaceType.level).all()

    @staticmethod
    def new(name, short_name, level):
        t = PlaceType(name, short_name, level)
        db.sesson.add(t)

place_parents = db.Table('place_parents',
    db.Column('parent_id', db.Integer, db.ForeignKey('place.id')),
    db.Column('child_id', db.Integer, db.ForeignKey('place.id'))
)

class Place(db.Model):
    __table_name__ = "place"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text, nullable=False)
    type_id = db.Column(db.Integer, db.ForeignKey('place_type.id'), nullable=False)
    type = db.relationship('PlaceType', foreign_keys=type_id,
        backref=db.backref('places', lazy='dynamic'))

    # immediate parent
    iparent_id = db.Column(db.Integer, db.ForeignKey('place.id'))
    iparent = db.relationship('Place', remote_side=[id],
        backref=db.backref('child_places', lazy='dynamic'))

    # List of parents
    # Required to list immediate children on the place page
    parents = db.relationship('Place', 
        secondary=place_parents, 
        primaryjoin=(id==place_parents.c.child_id),
        secondaryjoin=(id==place_parents.c.parent_id),
        backref=db.backref('places', lazy='dynamic', order_by='Place.key'),
        order_by='Place.id')

    def __init__(self, key, name, type):
        self.key = key
        self.name = name
        self.type = type

    def __repr__(self):
        return "Place(%r)" % self.key

    @staticmethod
    def find(key):
        return Place.query.filter_by(key=key).first()

    @staticmethod
    def get_toplevel_places():
        """Returns all places without any parent.
        """
        return Place.query.filter_by(iparent_id=None).all()

    def get_parent(self, type):
        """Returns parent place of given type.
        """
        try:
            return [p for p in self.parents if p.type == type][0]
        except IndexError:
            return None

    def get_places(self, type=None):
        """Returns all places of given type below this place.
        """
        return self._get_places_query(type=type).all()

    def get_places_count(self, type=None):
        return self._get_places_query(type=type).count()

    def _get_places_query(self, type=None):
        q = self.places
        if type:
            q = q.join(PlaceType).filter(PlaceType.id==type.id)
        return q

    def add_place(self, place):
        """Addes a new place as direct child of this place.

        This function takes care of setting parents for the 
        new place.
        """
        # The place is being added as an immediate child of this node.
        place.iparent = self
        # so, it's parents will be self.parents and self
        place.parents = self.parents + [self]
        db.session.add(place)

    def get_siblings(self):
        parents = sorted(self.parents, key=lambda p: p.type.level)
        if parents:
            return parents[-1].get_places(self.type)
        else:
            # top-level
            return Place.query.filter_by(type=self.type).all()

    def get_child_places_by_type(self):
        """Returns an iterator over type and child-places of that type 
        for all the immediate child places.
        """
        places = self.child_places.all()
        places.sort(key=lambda p: (p.type.level, p.key))
        return itertools.groupby(places, lambda p: p.type)

    def add_member(self, name, email, phone):
        """Adds a new member.

        The caller is responsible to call db.session.commit().
        """
        member = Member(self, name, email, phone)
        db.session.add(member)
        return member   

    def add_committee_type(self, place_type, name, description, slug):
        """Adds a new CommitteeType to this place.

        It is caller's responsibility to call db.session.commit().
        """
        c = CommitteeType(
                place=self,
                place_type=place_type,
                name=name,
                description=description,
                slug=slug)
        db.session.add(c)
        return c

    def get_committees(self):
        """Returns all committees at this place.
        """
        q = CommitteeType.query_by_place(self, recursive=True)
        committee_types = q.all()
        def get_committee(type):
            return type.committees.filter_by(place_id=self.id).first() or Committee(self, type)
        return [get_committee(type) for type in committee_types]

    def get_committee(self, slug):
        """Returns a committee with given slug.

        * If there is already a committee with that slug, it will be returned.
        * If there is no committee with that slug, but a committee structure
        is defined here or by a parent, a new committee instance will returned.
        * If neither a committe nor a committee strucutre is found for that
        slug, then None is returned.
        """
        committee_type = CommitteeType.find(self, slug, recursive=True)
        if committee_type:
            c = committee_type.committees.filter_by(place_id=self.id).first()
            if not c:
                c = Committee(self, committee_type)
            return c

class Member(db.Model):
    __table_name__ = "member"
    id = db.Column(db.Integer, primary_key=True)

    place_id = db.Column(db.Integer, db.ForeignKey('place.id'))
    place = db.relationship('Place', backref=db.backref('members', lazy='dynamic'))

    name = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text, unique=True)
    phone = db.Column(db.Text, nullable=False, unique=True)

    def __init__(self, place, name, email, phone):
        self.name = name
        self.email = email
        self.phone = phone
        self.place = place

    @staticmethod
    def find(email):
        return Member.query.filter_by(email=email).first()

class CommitteeType(db.Model):
    """Specification of a Committee.
    """
    __table_name__ = "committee_type"
    __table_args__ = (db.UniqueConstraint('place_id', 'slug'), {})

    id = db.Column(db.Integer, primary_key=True)

    # id of the place below which this committee can be created.
    place_id = db.Column(db.Integer, db.ForeignKey('place.id'))
    place = db.relationship('Place', backref=db.backref('committee_types', lazy='dynamic'))

    # A committee is always available for a type of places.
    # For example, a state can specify a committee that every ward can have.
    place_type_id = db.Column(db.Integer, db.ForeignKey('place_type.id'))
    place_type = db.relationship('PlaceType', foreign_keys=[place_type_id])

    # name and description of the committee
    name = db.Column(db.Text, nullable=False)
    slug = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)

    def __init__(self, place, place_type, name, description, slug):
        self.place = place
        self.place_type = place_type
        self.name = name
        self.description = description
        self.slug = slug

    def __repr__(self):
        return "<CommitteeType#{} - {} - {}>".format(self.id, self.place.key, self.name)

    def add_role(self, role_name, multiple, permission):
        """Adds a new role to this CommitteeType.

        The caller must call db.session.commit() explicitly to see these changes.
        """
        role = CommitteeRole(self, role_name, multiple, permission)
        db.session.add(role)

    @staticmethod
    def find(place, slug, recursive=False):
        """Returns CommitteeType defined at given place with given slug.

        If recursive=True, it tries to find the CommitteType at nearest parent,
        but make sures the committee_type matches the place_type.
        """
        q = CommitteeType.query_by_place(place, recursive=recursive).filter_by(slug=slug)
        return q.first()

    @staticmethod
    def query_by_place(place, recursive=True):
        """Returns a query object to query by place.

        If recursive=True, the returned query tries to find the committee_types
        at nearest parent, but make sures the committee_type matches the place_type.
        """
        if recursive:
            parents = [place] + place.parents
            parent_ids = [p.id for p in parents]

            # XXX-Anand
            # Taking the first matching row for now.
            # The right thing is to take the one the is nearest.
            # Will fix that later
            q = CommitteeType.query.filter(CommitteeType.place_id.in_(parent_ids))
            q = q.filter_by(place_type_id=place.type_id)
        else:
            q = CommitteeType.query.filter_by(place_id=place.id)
        return q

    @staticmethod
    def new_from_formdata(place, form):
        """Creates new CommitteeType instance from form data.
        """
        c = CommitteeType(place,
            place_type=PlaceType.get(form.level.data),
            name=form.name.data,
            description=form.description.data,
            slug=form.slug.data)
        db.session.add(c)
        for roledata in form.data['roles']:
            if roledata['name'].strip():
                c.add_role(
                    roledata['name'],
                    roledata['multiple'] == 'yes',
                    roledata['permission'])
        return c

class CommitteeRole(db.Model):
    """Role in a committee.

    A CommitteeType defines all roles that a committee is composed of.
    Right now there can be only one person for a role in the committee.
    Support for specify multiple members and min/max limits is yet to be
    implemented.
    """
    __table_name__ = "committee_role"
    id = db.Column(db.Integer, primary_key=True)
    committee_type_id = db.Column(db.Integer, db.ForeignKey('committee_type.id'))
    committee_type = db.relationship('CommitteeType', backref=db.backref('roles'))

    role = db.Column(db.Text)
    multiple = db.Column(db.Boolean)
    permission = db.Column(db.Text)

    def __init__(self, committee_type, role_name, multiple, permission):
        self.committee_type = committee_type
        self.role = role_name
        self.multiple = multiple
        self.permission = permission

class Committee(db.Model):
    """A real committee.

    The commitee structure is defined by the CommiteeType and a commitee can
    have members for each role defined by the CommitteeType.
    """
    id = db.Column(db.Integer, primary_key=True)

    # A committee is tied to a place
    place_id = db.Column(db.Integer, db.ForeignKey('place.id'))
    place = db.relationship('Place', foreign_keys=place_id,
        backref=db.backref('committees', lazy='dynamic'))

    # And specs of a committe are defined by a CommitteeType
    type_id = db.Column(db.Integer, db.ForeignKey('committee_type.id'))
    type = db.relationship('CommitteeType', foreign_keys=type_id,
        backref=db.backref('committees', lazy='dynamic'))

    def __init__(self, place, type):
        self.place = place
        self.type = type

class CommitteeMember(db.Model):
    """The members of a committee.
    """
    id = db.Column(db.Integer, primary_key=True)
    committee_id = db.Column(db.Integer, db.ForeignKey("committee.id"))
    committee = db.relationship('Committee', foreign_keys=committee_id,
        backref=db.backref('members'))

    member_id = db.Column(db.Integer, db.ForeignKey('member.id'))
    member = db.relationship('Member', foreign_keys=member_id,
        backref=db.backref('committees', lazy='dynamic'))

    role_id = db.Column(db.Integer, db.ForeignKey('committee_role.id'))
    role = db.relationship('CommitteeRole', foreign_keys=role_id,
        backref=db.backref('members', lazy='dynamic'))
